"""Smoke tests for the Weather Alert Dashboard."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from telemetry.models import AlertConfig, AlertHistory, Location, Telemetry
from telemetry.serializers import AlertConfigSerializer
from telemetry.tasks import evaluate_alerts, fetch_and_store_weather, send_alert_email


User = get_user_model()


class ModelSmokeTests(TestCase):
    """Minimal coverage for the core models."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="smoke", password="secret", email="smoke@example.com"
        )
        self.location = Location.objects.create(
            name="Istanbul", latitude=41.0, longitude=29.0, added_by_user=self.user
        )

    def test_location_str_contains_name(self):
        self.assertIn("Istanbul", str(self.location))

    def test_telemetry_unique_constraint(self):
        stamp = timezone.now().replace(microsecond=0)
        Telemetry.objects.create(location=self.location, timestamp=stamp)
        with self.assertRaises(Exception):
            Telemetry.objects.create(location=self.location, timestamp=stamp)


class SerializerValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="serializer", password="secret")
        self.location = Location.objects.create(name="Berlin", added_by_user=self.user)

    def test_alert_config_serializer_accepts_valid_threshold(self):
        serializer = AlertConfigSerializer(
            data={
                "location": self.location.id,
                "threshold_type": "temp_gt",
                "threshold_value": 10,
                "is_active": True,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class LocationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api", password="secret")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_auth_required_for_locations(self):
        anon = APIClient()
        resp = anon.get("/api/locations/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("telemetry.views.fetch_current_by_coords")
    def test_create_location_fetches_initial_weather(self, mock_fetch):
        mock_fetch.return_value = {"temperature_c": 20.0, "wind_speed_ms": 5.0, "humidity": 50.0}
        resp = self.client.post(
            "/api/locations/",
            {"name": "Zero", "latitude": 0.0, "longitude": 0.0},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(mock_fetch.called)


class WeatherApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="weather", password="secret")
        self.location = Location.objects.create(
            name="Tokyo", latitude=35.0, longitude=139.0, added_by_user=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_weather_endpoint_returns_series(self):
        Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=22.0,
            wind_speed_ms=4.0,
            humidity=60.0,
        )
        resp = self.client.get(f"/api/weather/{self.location.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("series", resp.data)
        self.assertEqual(resp.data["location"]["name"], "Tokyo")


class AlertConfigApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alerts", password="secret")
        self.location = Location.objects.create(name="Sydney", added_by_user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_alert_config(self):
        payload = {
            "location": self.location.id,
            "threshold_type": "temp_gt",
            "threshold_value": 30,
            "is_active": True,
        }
        resp = self.client.post("/api/alerts/config/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            AlertConfig.objects.filter(location=self.location, threshold_type="temp_gt").exists()
        )

    def test_alert_history_endpoint(self):
        AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="temp_gt",
            value=35.0,
            user_notified=True,
        )
        resp = self.client.get("/api/alerts/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)


class HtmlViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="html", password="secret")
        self.client = Client()
        self.client.force_login(self.user)
        self.location = Location.objects.create(
            name="London", latitude=51.5, longitude=-0.12, added_by_user=self.user
        )

    def test_dashboard_renders(self):
        Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=15.0,
            wind_speed_ms=3.0,
            humidity=70.0,
        )
        resp = self.client.get("/dashboard/")
        self.assertContains(resp, "Weather Dashboard")

    def test_location_historical_view(self):
        Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now() - timedelta(hours=1),
            temperature_c=12.0,
            wind_speed_ms=2.0,
            humidity=65.0,
        )
        resp = self.client.get(f"/locations-page/{self.location.id}/historical/")
        self.assertContains(resp, "Historical Weather")


class TaskSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="worker", password="secret", email="worker@example.com")
        self.location = Location.objects.create(
            name="Worker City", latitude=40.0, longitude=-74.0, added_by_user=self.user
        )

    @patch("telemetry.tasks.fetch_current_by_coords")
    def test_fetch_and_store_weather(self, mock_fetch):
        mock_fetch.return_value = {"temperature_c": 25.0, "wind_speed_ms": 8.0, "humidity": 55.0}
        fetch_and_store_weather()
        self.assertTrue(Telemetry.objects.filter(location=self.location).exists())

    @override_settings(ALERT_NOTIFICATION_EMAIL="alerts@example.com")
    @patch("telemetry.tasks.send_mail")
    @patch("telemetry.tasks._publish_update")
    def test_evaluate_alerts_triggers_email(self, mock_publish, mock_send_mail):
        mock_send_mail.return_value = 1
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
        )
        measurement = Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=35.0,
            wind_speed_ms=5.0,
            humidity=40.0,
        )
        evaluate_alerts(self.location, measurement)
        self.assertTrue(mock_send_mail.called)
        self.assertEqual(AlertHistory.objects.filter(location=self.location).count(), 1)


class SendAlertEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="emailer", password="secret", email="user@example.com"
        )
        self.location = Location.objects.create(name="Email City", added_by_user=self.user)
        self.config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
        )

    @override_settings(ALERT_NOTIFICATION_EMAIL="alerts@example.com", DEFAULT_FROM_EMAIL="noreply@example.com")
    @patch("telemetry.tasks.send_mail")
    def test_overridden_recipient(self, mock_send_mail):
        mock_send_mail.return_value = 1
        send_alert_email(self.config, self.location, 34.0)
        args, _ = mock_send_mail.call_args
        self.assertEqual(args[2], "noreply@example.com")
        self.assertEqual(args[3], ["alerts@example.com"])

    @override_settings(ALERT_NOTIFICATION_EMAIL=None, DEFAULT_FROM_EMAIL="alerts@example.com")
    @patch("telemetry.tasks.send_mail")
    def test_falls_back_to_user_email(self, mock_send_mail):
        mock_send_mail.return_value = 1
        send_alert_email(self.config, self.location, 34.0)
        args, _ = mock_send_mail.call_args
        self.assertEqual(args[3], ["user@example.com"])

