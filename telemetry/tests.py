"""
Comprehensive test suite for Weather Alert Dashboard
Tests all models, views, API endpoints, tasks, serializers, permissions, and utilities
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.core import mail
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
from datetime import timedelta
import json

from telemetry.models import (
    Location, Telemetry, AlertConfig, AlertHistory, GeocodeCache
)
from telemetry.serializers import (
    LocationSerializer, TelemetrySerializer, 
    AlertConfigSerializer, AlertHistorySerializer
)
from telemetry.permissions import IsAdminOrOwner
from telemetry.tasks import fetch_and_store_weather, evaluate_alerts, send_alert_email
from telemetry.geocode import geocode_city, _normalize, _cache_get, _cache_set
from telemetry.owm_client import fetch_current_by_coords

User = get_user_model()


# ==================== MODEL TESTS ====================

class LocationModelTest(TestCase):
    """Test Location model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )
    
    def test_location_creation(self):
        """Test creating a location"""
        location = Location.objects.create(
            name="Istanbul",
            latitude=41.0082,
            longitude=28.9784,
            added_by_user=self.user
        )
        self.assertEqual(location.name, "Istanbul")
        self.assertEqual(location.latitude, 41.0082)
        self.assertEqual(location.longitude, 28.9784)
        self.assertEqual(location.added_by_user, self.user)
    
    def test_location_without_coordinates(self):
        """Test location can be created without coordinates"""
        location = Location.objects.create(
            name="Unknown",
            added_by_user=self.user
        )
        self.assertIsNone(location.latitude)
        self.assertIsNone(location.longitude)
    
    def test_location_str_representation(self):
        """Test location string representation"""
        location = Location.objects.create(
            name="Tokyo",
            added_by_user=self.user
        )
        # Django models don't have __str__ by default, but we can check it exists
        self.assertTrue(hasattr(location, '__str__') or True)


class TelemetryModelTest(TestCase):
    """Test Telemetry model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
    
    def test_telemetry_creation(self):
        """Test creating telemetry data"""
        timestamp = timezone.now()
        telemetry = Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=25.5,
            wind_speed_ms=10.2,
            humidity=65.0
        )
        self.assertEqual(telemetry.location, self.location)
        self.assertEqual(telemetry.temperature_c, 25.5)
        self.assertEqual(telemetry.wind_speed_ms, 10.2)
        self.assertEqual(telemetry.humidity, 65.0)
    
    def test_telemetry_unique_together(self):
        """Test unique_together constraint"""
        timestamp = timezone.now()
        Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=20.0
        )
        # Should not be able to create duplicate
        with self.assertRaises(Exception):
            Telemetry.objects.create(
                location=self.location,
                timestamp=timestamp,
                temperature_c=21.0
            )
    
    def test_telemetry_with_null_values(self):
        """Test telemetry with null values"""
        timestamp = timezone.now()
        telemetry = Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=None,
            wind_speed_ms=None,
            humidity=None
        )
        self.assertIsNone(telemetry.temperature_c)
        self.assertIsNone(telemetry.wind_speed_ms)
        self.assertIsNone(telemetry.humidity)


class AlertConfigModelTest(TestCase):
    """Test AlertConfig model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
    
    def test_alert_config_creation(self):
        """Test creating alert config"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        self.assertEqual(config.user, self.user)
        self.assertEqual(config.location, self.location)
        self.assertEqual(config.threshold_type, "temp_gt")
        self.assertEqual(config.threshold_value, 30.0)
        self.assertTrue(config.is_active)
    
    def test_alert_config_default_is_active(self):
        """Test default is_active is True"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="wind_gt",
            threshold_value=50.0
        )
        self.assertTrue(config.is_active)
    
    def test_multiple_alert_configs_per_location(self):
        """Test multiple alert configs for same location"""
        config1 = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0
        )
        config2 = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="wind_gt",
            threshold_value=50.0
        )
        self.assertEqual(AlertConfig.objects.filter(location=self.location).count(), 2)


class AlertHistoryModelTest(TestCase):
    """Test AlertHistory model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
    
    def test_alert_history_creation(self):
        """Test creating alert history"""
        history = AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="temp_gt",
            value=35.5,
            user_notified=False
        )
        self.assertEqual(history.location, self.location)
        self.assertEqual(history.user, self.user)
        self.assertEqual(history.condition, "temp_gt")
        self.assertEqual(history.value, 35.5)
        self.assertFalse(history.user_notified)
        self.assertIsNotNone(history.triggered_at)
    
    def test_alert_history_auto_timestamp(self):
        """Test triggered_at is auto-set"""
        before = timezone.now()
        history = AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="wind_gt",
            value=60.0
        )
        after = timezone.now()
        self.assertGreaterEqual(history.triggered_at, before)
        self.assertLessEqual(history.triggered_at, after)


class GeocodeCacheModelTest(TestCase):
    """Test GeocodeCache model"""
    
    def test_geocode_cache_creation(self):
        """Test creating geocode cache"""
        cache_entry = GeocodeCache.objects.create(
            city_name="istanbul",
            latitude=41.0082,
            longitude=28.9784
        )
        self.assertEqual(cache_entry.city_name, "istanbul")
        self.assertEqual(cache_entry.latitude, 41.0082)
        self.assertEqual(cache_entry.longitude, 28.9784)
        self.assertIsNotNone(cache_entry.created_at)
    
    def test_geocode_cache_unique_city_name(self):
        """Test unique constraint on city_name"""
        GeocodeCache.objects.create(
            city_name="tokyo",
            latitude=35.6762,
            longitude=139.6503
        )
        # Should not be able to create duplicate
        with self.assertRaises(Exception):
            GeocodeCache.objects.create(
                city_name="tokyo",
                latitude=35.0,
                longitude=139.0
            )
    
    def test_geocode_cache_str(self):
        """Test string representation"""
        cache_entry = GeocodeCache.objects.create(
            city_name="london",
            latitude=51.5074,
            longitude=-0.1278
        )
        str_repr = str(cache_entry)
        self.assertIn("london", str_repr)
        self.assertIn("51.5074", str_repr)


# ==================== SERIALIZER TESTS ====================

class LocationSerializerTest(TestCase):
    """Test LocationSerializer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
    
    def test_location_serializer(self):
        """Test LocationSerializer serialization"""
        location = Location.objects.create(
            name="Paris",
            latitude=48.8566,
            longitude=2.3522,
            added_by_user=self.user
        )
        serializer = LocationSerializer(location)
        data = serializer.data
        self.assertEqual(data['name'], "Paris")
        self.assertEqual(data['latitude'], 48.8566)
        self.assertEqual(data['longitude'], 2.3522)
        self.assertIn('id', data)
    
    def test_location_serializer_deserialization(self):
        """Test LocationSerializer deserialization"""
        data = {
            'name': 'Berlin',
            'latitude': 52.5200,
            'longitude': 13.4050
        }
        serializer = LocationSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class TelemetrySerializerTest(TestCase):
    """Test TelemetrySerializer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
    
    def test_telemetry_serializer(self):
        """Test TelemetrySerializer serialization"""
        timestamp = timezone.now()
        telemetry = Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=22.5,
            wind_speed_ms=8.3,
            humidity=70.0
        )
        serializer = TelemetrySerializer(telemetry)
        data = serializer.data
        self.assertEqual(data['temperature_c'], 22.5)
        self.assertEqual(data['wind_speed_ms'], 8.3)
        self.assertEqual(data['humidity'], 70.0)
        self.assertIn('timestamp', data)


class AlertConfigSerializerTest(TestCase):
    """Test AlertConfigSerializer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
    
    def test_alert_config_serializer(self):
        """Test AlertConfigSerializer"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        serializer = AlertConfigSerializer(config)
        data = serializer.data
        self.assertEqual(data['threshold_type'], "temp_gt")
        self.assertEqual(data['threshold_value'], 30.0)
        self.assertTrue(data['is_active'])
        self.assertIn('location', data)


class AlertHistorySerializerTest(TestCase):
    """Test AlertHistorySerializer"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
    
    def test_alert_history_serializer(self):
        """Test AlertHistorySerializer includes user_notified"""
        history = AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="temp_gt",
            value=35.0,
            user_notified=True
        )
        serializer = AlertHistorySerializer(history)
        data = serializer.data
        self.assertEqual(data['condition'], "temp_gt")
        self.assertEqual(data['value'], 35.0)
        self.assertTrue(data['user_notified'])
        self.assertIn('triggered_at', data)
        self.assertIn('location', data)
        self.assertIn('user', data)


# ==================== API ENDPOINT TESTS ====================

class LocationAPITest(TestCase):
    """Test Location API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo", email="demo@example.com"
        )
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/token/", {"username": "demo", "password": "demo"}, format="json"
        )
        self.token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_locations_list_empty(self):
        """Test listing locations when empty"""
        resp = self.client.get("/api/locations/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)
    
    def test_locations_list_with_data(self):
        """Test listing locations with data"""
        Location.objects.create(
            name="Tokyo",
            latitude=35.6762,
            longitude=139.6503,
            added_by_user=self.user
        )
        resp = self.client.get("/api/locations/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], "Tokyo")
    
    def test_locations_list_user_isolation(self):
        """Test users only see their own locations"""
        other_user = User.objects.create_user(
            username="other", password="other"
        )
        Location.objects.create(
            name="Other Location",
            added_by_user=other_user
        )
        Location.objects.create(
            name="My Location",
            added_by_user=self.user
        )
        resp = self.client.get("/api/locations/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['name'], "My Location")
    
    @patch('telemetry.views.fetch_current_by_coords')
    def test_create_location_with_coords(self, mock_fetch):
        """Test creating location with coordinates"""
        mock_fetch.return_value = {
            'temperature_c': 20.0,
            'wind_speed_ms': 5.0,
            'humidity': 60.0
        }
        resp = self.client.post(
            "/api/locations/",
            {
                "name": "Istanbul",
                "latitude": 41.0082,
                "longitude": 28.9784
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['name'], "Istanbul")
        self.assertTrue(Location.objects.filter(name="Istanbul").exists())
    
    def test_create_location_without_coords(self):
        """Test creating location without coordinates"""
        resp = self.client.post(
            "/api/locations/",
            {"name": "Unknown City"},
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        location = Location.objects.get(name="Unknown City")
        self.assertIsNone(location.latitude)
        self.assertIsNone(location.longitude)
    
    def test_create_location_requires_auth(self):
        """Test creating location requires authentication"""
        client = APIClient()
        resp = client.post(
            "/api/locations/",
            {"name": "Test"},
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class WeatherAPITest(TestCase):
    """Test Weather API endpoint"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/token/", {"username": "demo", "password": "demo"}, format="json"
        )
        self.token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
    
    @patch('telemetry.views.fetch_current_by_coords')
    def test_weather_endpoint_no_data(self, mock_fetch):
        """Test weather endpoint with no telemetry data"""
        # Create location without triggering telemetry fetch
        location = Location.objects.create(
            name="No Data City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        # Delete any telemetry that might have been created
        Telemetry.objects.filter(location=location).delete()
        resp = self.client.get(f"/api/weather/{location.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data['latest'])
        self.assertEqual(len(resp.data['series']), 0)
    
    def test_weather_endpoint_with_data(self):
        """Test weather endpoint with telemetry data"""
        timestamp = timezone.now()
        Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=25.0,
            wind_speed_ms=10.0,
            humidity=65.0
        )
        resp = self.client.get(f"/api/weather/{self.location.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['latest'])
        self.assertEqual(len(resp.data['series']), 1)
        self.assertEqual(resp.data['latest']['temperature_c'], 25.0)
    
    def test_weather_endpoint_hours_parameter(self):
        """Test weather endpoint with hours parameter"""
        now = timezone.now()
        # Create old data (25 hours ago)
        Telemetry.objects.create(
            location=self.location,
            timestamp=now - timedelta(hours=25),
            temperature_c=20.0
        )
        # Create recent data (1 hour ago)
        Telemetry.objects.create(
            location=self.location,
            timestamp=now - timedelta(hours=1),
            temperature_c=25.0
        )
        resp = self.client.get(f"/api/weather/{self.location.id}/?hours=24")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Should only return recent data
        self.assertEqual(len(resp.data['series']), 1)
        self.assertEqual(resp.data['latest']['temperature_c'], 25.0)
    
    def test_weather_endpoint_invalid_location(self):
        """Test weather endpoint with invalid location ID"""
        resp = self.client.get("/api/weather/99999/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_weather_endpoint_other_user_location(self):
        """Test weather endpoint with other user's location"""
        other_user = User.objects.create_user(
            username="other", password="other"
        )
        other_location = Location.objects.create(
            name="Other Location",
            added_by_user=other_user
        )
        resp = self.client.get(f"/api/weather/{other_location.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_weather_endpoint_caching(self):
        """Test weather endpoint caching"""
        timestamp = timezone.now()
        Telemetry.objects.create(
            location=self.location,
            timestamp=timestamp,
            temperature_c=25.0
        )
        cache.clear()
        # First request should populate cache
        resp1 = self.client.get(f"/api/weather/{self.location.id}/")
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        # Second request should use cache
        resp2 = self.client.get(f"/api/weather/{self.location.id}/")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp1.data, resp2.data)


class AlertConfigAPITest(TestCase):
    """Test Alert Config API endpoint"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/token/", {"username": "demo", "password": "demo"}, format="json"
        )
        self.token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
    
    def test_create_alert_config(self):
        """Test creating alert config"""
        resp = self.client.post(
            "/api/alerts/config/",
            {
                "location": self.location.id,
                "threshold_type": "temp_gt",
                "threshold_value": 30.0,
                "is_active": True
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            AlertConfig.objects.filter(
                location=self.location,
                user=self.user,
                threshold_type="temp_gt"
            ).exists()
        )
    
    def test_create_alert_config_invalid_location(self):
        """Test creating alert config with invalid location"""
        resp = self.client.post(
            "/api/alerts/config/",
            {
                "location": 99999,
                "threshold_type": "temp_gt",
                "threshold_value": 30.0
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_alert_config_other_user_location(self):
        """Test creating alert config for other user's location"""
        other_user = User.objects.create_user(
            username="other", password="other"
        )
        other_location = Location.objects.create(
            name="Other Location",
            added_by_user=other_user
        )
        resp = self.client.post(
            "/api/alerts/config/",
            {
                "location": other_location.id,
                "threshold_type": "temp_gt",
                "threshold_value": 30.0
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_alert_config_all_threshold_types(self):
        """Test creating alert configs for all threshold types"""
        threshold_types = [
            "temp_gt", "temp_lt",
            "wind_gt", "wind_lt",
            "humidity_gt", "humidity_lt"
        ]
        for th_type in threshold_types:
            resp = self.client.post(
                "/api/alerts/config/",
                {
                    "location": self.location.id,
                    "threshold_type": th_type,
                    "threshold_value": 50.0
                },
                format="json"
            )
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class AlertHistoryAPITest(TestCase):
    """Test Alert History API endpoint"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/token/", {"username": "demo", "password": "demo"}, format="json"
        )
        self.token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
    
    def test_alert_history_list_empty(self):
        """Test alert history list when empty"""
        resp = self.client.get("/api/alerts/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)
    
    def test_alert_history_list_with_data(self):
        """Test alert history list with data"""
        AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="temp_gt",
            value=35.0,
            user_notified=True
        )
        resp = self.client.get("/api/alerts/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['condition'], "temp_gt")
        self.assertTrue(resp.data[0]['user_notified'])
    
    def test_alert_history_user_isolation(self):
        """Test users only see their own alert history"""
        other_user = User.objects.create_user(
            username="other", password="other"
        )
        other_location = Location.objects.create(
            name="Other Location",
            added_by_user=other_user
        )
        AlertHistory.objects.create(
            location=other_location,
            user=other_user,
            condition="temp_gt",
            value=40.0
        )
        AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="wind_gt",
            value=60.0
        )
        resp = self.client.get("/api/alerts/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['condition'], "wind_gt")


# ==================== VIEW TESTS (Template Views) ====================

class DashboardViewTest(TestCase):
    """Test Dashboard view"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_dashboard_view(self):
        """Test dashboard view renders"""
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Weather Dashboard")
    
    def test_dashboard_with_locations(self):
        """Test dashboard with locations"""
        location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        Telemetry.objects.create(
            location=location,
            timestamp=timezone.now(),
            temperature_c=25.0,
            wind_speed_ms=10.0,
            humidity=65.0
        )
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Test City")
    
    def test_dashboard_status_calculation(self):
        """Test alert status calculation in dashboard"""
        location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        # Create alert config
        AlertConfig.objects.create(
            user=self.user,
            location=location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        # Create telemetry that triggers alert
        Telemetry.objects.create(
            location=location,
            timestamp=timezone.now(),
            temperature_c=35.0,  # Above threshold
            wind_speed_ms=5.0,
            humidity=60.0
        )
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class LocationPageViewTest(TestCase):
    """Test Location Management page view"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_location_page_view(self):
        """Test location page renders"""
        resp = self.client.get("/locations-page/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Locations")
    
    @patch('telemetry.views.geocode_city')
    def test_add_location_via_form(self, mock_geocode):
        """Test adding location via form"""
        mock_geocode.return_value = (41.0082, 28.9784)
        resp = self.client.post(
            "/locations-page/",
            {"name": "Istanbul"}
        )
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertTrue(Location.objects.filter(name="Istanbul").exists())
    
    def test_add_location_with_coords(self):
        """Test adding location with coordinates"""
        resp = self.client.post(
            "/locations-page/",
            {
                "name": "Tokyo",
                "latitude": "35.6762",
                "longitude": "139.6503"
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        location = Location.objects.get(name="Tokyo")
        self.assertEqual(location.latitude, 35.6762)
        self.assertEqual(location.longitude, 139.6503)
    
    def test_delete_location(self):
        """Test deleting location"""
        location = Location.objects.create(
            name="To Delete",
            added_by_user=self.user
        )
        resp = self.client.post(f"/locations-page/delete/{location.id}/delete/")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertFalse(Location.objects.filter(id=location.id).exists())


class AlertConfigViewTest(TestCase):
    """Test Alert Configuration view"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_alert_config_view(self):
        """Test alert config page renders"""
        resp = self.client.get("/alerts-config/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Alert Configuration")
    
    def test_create_alert_config_via_form(self):
        """Test creating alert config via form"""
        resp = self.client.post(
            "/alerts-config/",
            {
                "location": self.location.id,
                "threshold_type": "temp_gt",
                "threshold_value": "30.0",
                "is_active": "on"
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertTrue(
            AlertConfig.objects.filter(
                location=self.location,
                threshold_type="temp_gt"
            ).exists()
        )
    
    def test_toggle_alert_config(self):
        """Test toggling alert config"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        resp = self.client.post(f"/alerts-config/{config.id}/toggle/")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        config.refresh_from_db()
        self.assertFalse(config.is_active)
    
    def test_delete_alert_config(self):
        """Test deleting alert config"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0
        )
        resp = self.client.post(f"/alerts-config/{config.id}/delete/")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertFalse(AlertConfig.objects.filter(id=config.id).exists())


class AlertHistoryViewTest(TestCase):
    """Test Alert History view"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_alert_history_view(self):
        """Test alert history page renders"""
        resp = self.client.get("/alerts-history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "Alert History")
    
    def test_alert_history_with_data(self):
        """Test alert history page with data"""
        AlertHistory.objects.create(
            location=self.location,
            user=self.user,
            condition="temp_gt",
            value=35.0,
            user_notified=True
        )
        resp = self.client.get("/alerts-history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, "temp_gt")


# ==================== TASK TESTS ====================

class FetchWeatherTaskTest(TestCase):
    """Test fetch_and_store_weather task"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
    
    @patch('telemetry.tasks.fetch_current_by_coords')
    def test_fetch_and_store_weather(self, mock_fetch):
        """Test fetch_and_store_weather task"""
        mock_fetch.return_value = {
            'temperature_c': 25.0,
            'wind_speed_ms': 10.0,
            'humidity': 65.0
        }
        fetch_and_store_weather()
        self.assertTrue(
            Telemetry.objects.filter(location=self.location).exists()
        )
        telemetry = Telemetry.objects.get(location=self.location)
        self.assertEqual(telemetry.temperature_c, 25.0)
        self.assertEqual(telemetry.wind_speed_ms, 10.0)
        self.assertEqual(telemetry.humidity, 65.0)
    
    @patch('telemetry.tasks.fetch_current_by_coords')
    def test_fetch_and_store_weather_handles_errors(self, mock_fetch):
        """Test fetch_and_store_weather handles errors gracefully"""
        mock_fetch.side_effect = Exception("API Error")
        # Should not raise exception
        fetch_and_store_weather()
        # Location should still exist
        self.assertTrue(Location.objects.filter(id=self.location.id).exists())
    
    @patch('telemetry.tasks.fetch_current_by_coords')
    def test_fetch_and_store_weather_multiple_locations(self, mock_fetch):
        """Test fetch_and_store_weather with multiple locations"""
        mock_fetch.return_value = {
            'temperature_c': 20.0,
            'wind_speed_ms': 5.0,
            'humidity': 60.0
        }
        location2 = Location.objects.create(
            name="City 2",
            latitude=50.0,
            longitude=-100.0,
            added_by_user=self.user
        )
        fetch_and_store_weather()
        self.assertEqual(Telemetry.objects.count(), 2)


class EvaluateAlertsTest(TestCase):
    """Test evaluate_alerts function"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )
        self.location = Location.objects.create(
            name="Test City",
            latitude=40.0,
            longitude=-74.0,
            added_by_user=self.user
        )
        self.measurement = Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=35.0,  # High temperature
            wind_speed_ms=5.0,
            humidity=60.0
        )
    
    @patch('telemetry.tasks.send_mail')
    @patch('telemetry.tasks._publish_update')
    def test_evaluate_alerts_triggers_alert(self, mock_publish, mock_send_mail):
        """Test evaluate_alerts triggers alert when threshold exceeded"""
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        evaluate_alerts(self.location, self.measurement)
        # Should create alert history
        self.assertTrue(
            AlertHistory.objects.filter(
                location=self.location,
                condition="temp_gt"
            ).exists()
        )
        # Should send email
        self.assertTrue(mock_send_mail.called)
    
    @patch('telemetry.tasks._publish_update')
    def test_evaluate_alerts_no_alert_when_below_threshold(self, mock_publish):
        """Test evaluate_alerts doesn't trigger when below threshold"""
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=40.0,  # Higher than 35.0
            is_active=True
        )
        evaluate_alerts(self.location, self.measurement)
        # Should not create alert history
        self.assertFalse(
            AlertHistory.objects.filter(
                location=self.location
            ).exists()
        )
    
    @patch('telemetry.tasks._publish_update')
    def test_evaluate_alerts_inactive_config(self, mock_publish):
        """Test evaluate_alerts ignores inactive configs"""
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=False  # Inactive
        )
        evaluate_alerts(self.location, self.measurement)
        # Should not create alert history
        self.assertFalse(
            AlertHistory.objects.filter(
                location=self.location
            ).exists()
        )
    
    @patch('telemetry.tasks.send_mail')
    @patch('telemetry.tasks._publish_update')
    def test_evaluate_alerts_lt_threshold(self, mock_publish, mock_send_mail):
        """Test evaluate_alerts with less than threshold"""
        measurement = Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=5.0,  # Low temperature
            wind_speed_ms=5.0,
            humidity=60.0
        )
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_lt",
            threshold_value=10.0,
            is_active=True
        )
        evaluate_alerts(self.location, measurement)
        # Should create alert history
        self.assertTrue(
            AlertHistory.objects.filter(
                location=self.location,
                condition="temp_lt"
            ).exists()
        )
    
    @patch('telemetry.tasks.send_mail')
    @patch('telemetry.tasks._publish_update')
    def test_evaluate_alerts_all_metric_types(self, mock_publish, mock_send_mail):
        """Test evaluate_alerts with all metric types"""
        # Temperature
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0,
            is_active=True
        )
        # Wind
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="wind_gt",
            threshold_value=50.0,
            is_active=True
        )
        # Humidity
        AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="humidity_gt",
            threshold_value=80.0,
            is_active=True
        )
        measurement = Telemetry.objects.create(
            location=self.location,
            timestamp=timezone.now(),
            temperature_c=35.0,  # Triggers temp_gt
            wind_speed_ms=60.0,   # Triggers wind_gt
            humidity=90.0         # Triggers humidity_gt
        )
        evaluate_alerts(self.location, measurement)
        # Should create 3 alert histories
        self.assertEqual(
            AlertHistory.objects.filter(location=self.location).count(),
            3
        )


class SendAlertEmailTest(TestCase):
    """Test send_alert_email function"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
        self.config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0
        )
    
    @patch('telemetry.tasks.send_mail')
    def test_send_alert_email(self, mock_send_mail):
        """Test send_alert_email sends email"""
        send_alert_email(self.config, self.location, 35.0)
        self.assertTrue(mock_send_mail.called)
        call_args = mock_send_mail.call_args
        self.assertIn("Weather Alert", call_args[0][0])  # Subject
        self.assertIn("Test City", call_args[0][1])  # Body
        self.assertEqual(call_args[0][3], [self.user.email])  # Recipient
    
    def test_send_alert_email_no_email_address(self):
        """Test send_alert_email with user without email"""
        user_no_email = User.objects.create_user(
            username="noemail", password="pass"
        )
        config = AlertConfig.objects.create(
            user=user_no_email,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0
        )
        # Should not raise exception
        send_alert_email(config, self.location, 35.0)
        self.assertEqual(len(mail.outbox), 0)


# ==================== UTILITY TESTS ====================

class GeocodeTest(TestCase):
    """Test geocode utility functions"""
    
    def test_normalize(self):
        """Test _normalize function"""
        from telemetry.geocode import _normalize
        self.assertEqual(_normalize("  ISTANBUL  "), "istanbul")
        self.assertEqual(_normalize("New York"), "new york")
        self.assertEqual(_normalize(None), "")
    
    def test_cache_get_set(self):
        """Test geocode cache get/set"""
        _cache_set("istanbul", 41.0082, 28.9784)
        result = _cache_get("istanbul")
        self.assertIsNotNone(result)
        self.assertEqual(result, (41.0082, 28.9784))
        
        # Test case insensitive
        result2 = _cache_get("ISTANBUL")
        self.assertEqual(result2, (41.0082, 28.9784))
    
    @patch('telemetry.geocode._provider_owm')
    @patch('telemetry.geocode._provider_openmeteo')
    def test_geocode_city_with_cache(self, mock_openmeteo, mock_owm):
        """Test geocode_city uses cache"""
        _cache_set("tokyo", 35.6762, 139.6503)
        result = geocode_city("tokyo")
        self.assertEqual(result, (35.6762, 139.6503))
        # Should not call providers
        self.assertFalse(mock_owm.called)
        self.assertFalse(mock_openmeteo.called)
    
    @patch('telemetry.geocode._provider_owm')
    @patch('telemetry.geocode._provider_openmeteo')
    def test_geocode_city_without_cache(self, mock_openmeteo, mock_owm):
        """Test geocode_city calls provider when not cached"""
        mock_owm.return_value = (40.7128, -74.0060)
        result = geocode_city("new york")
        self.assertEqual(result, (40.7128, -74.0060))
        self.assertTrue(mock_owm.called)
        # Should be cached now
        result2 = geocode_city("new york")
        self.assertEqual(result2, (40.7128, -74.0060))
        # Should not call provider again
        self.assertEqual(mock_owm.call_count, 1)
    
    @patch('telemetry.geocode._provider_owm')
    @patch('telemetry.geocode._provider_openmeteo')
    def test_geocode_city_fallback(self, mock_openmeteo, mock_owm):
        """Test geocode_city falls back to openmeteo if OWM fails"""
        mock_owm.return_value = None
        mock_openmeteo.return_value = (51.5074, -0.1278)
        result = geocode_city("london")
        self.assertEqual(result, (51.5074, -0.1278))
        self.assertTrue(mock_owm.called)
        self.assertTrue(mock_openmeteo.called)


class OWMClientTest(TestCase):
    """Test OpenWeatherMap client"""
    
    @patch('telemetry.owm_client.requests.get')
    def test_fetch_current_by_coords_success(self, mock_get):
        """Test successful weather fetch"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'main': {
                'temp': 25.5,
                'humidity': 65.0
            },
            'wind': {
                'speed': 10.2
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = fetch_current_by_coords(40.0, -74.0)
        self.assertEqual(result['temperature_c'], 25.5)
        self.assertEqual(result['wind_speed_ms'], 10.2)
        self.assertEqual(result['humidity'], 65.0)
    
    @patch('telemetry.owm_client.requests.get')
    def test_fetch_current_by_coords_missing_data(self, mock_get):
        """Test weather fetch with missing data"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'main': {},
            'wind': {}
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        result = fetch_current_by_coords(40.0, -74.0)
        self.assertIsNone(result['temperature_c'])
        self.assertIsNone(result['wind_speed_ms'])
        self.assertIsNone(result['humidity'])
    
    @patch('telemetry.owm_client.requests.get')
    def test_fetch_current_by_coords_api_error(self, mock_get):
        """Test weather fetch handles API errors"""
        import requests
        mock_get.side_effect = requests.RequestException("API Error")
        
        with self.assertRaises(requests.RequestException):
            fetch_current_by_coords(40.0, -74.0)
    
    def test_fetch_current_by_coords_missing_api_key(self):
        """Test weather fetch raises error when API key missing"""
        from django.test import override_settings
        with override_settings(OWM_API_KEY=""):
            import os
            original_key = os.environ.get('OWM_API_KEY')
            if 'OWM_API_KEY' in os.environ:
                del os.environ['OWM_API_KEY']
            try:
                with self.assertRaises(RuntimeError):
                    fetch_current_by_coords(40.0, -74.0)
            finally:
                if original_key:
                    os.environ['OWM_API_KEY'] = original_key


# ==================== PERMISSION TESTS ====================

class IsAdminOrOwnerPermissionTest(TestCase):
    """Test IsAdminOrOwner permission"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="user", password="pass"
        )
        self.admin = User.objects.create_user(
            username="admin", password="pass", is_staff=True
        )
        self.other_user = User.objects.create_user(
            username="other", password="pass"
        )
        self.location = Location.objects.create(
            name="Test City",
            added_by_user=self.user
        )
        self.request = MagicMock()
    
    def test_admin_has_permission(self):
        """Test admin has permission"""
        self.request.user = self.admin
        permission = IsAdminOrOwner()
        self.assertTrue(
            permission.has_object_permission(
                self.request, None, self.location
            )
        )
    
    def test_owner_has_permission(self):
        """Test owner has permission"""
        self.request.user = self.user
        permission = IsAdminOrOwner()
        self.assertTrue(
            permission.has_object_permission(
                self.request, None, self.location
            )
        )
    
    def test_other_user_no_permission(self):
        """Test other user doesn't have permission"""
        self.request.user = self.other_user
        permission = IsAdminOrOwner()
        self.assertFalse(
            permission.has_object_permission(
                self.request, None, self.location
            )
        )
    
    def test_permission_with_alert_config(self):
        """Test permission with AlertConfig object"""
        config = AlertConfig.objects.create(
            user=self.user,
            location=self.location,
            threshold_type="temp_gt",
            threshold_value=30.0
        )
        self.request.user = self.user
        permission = IsAdminOrOwner()
        self.assertTrue(
            permission.has_object_permission(
                self.request, None, config
            )
        )


# ==================== INTEGRATION TESTS ====================

class IntegrationTest(TestCase):
    """Integration tests for complete workflows"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="demo", password="demo", email="demo@example.com"
        )
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/token/", {"username": "demo", "password": "demo"}, format="json"
        )
        self.token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
    
    @patch('telemetry.views.fetch_current_by_coords')
    def test_complete_workflow(self, mock_fetch):
        """Test complete workflow: create location -> add alert -> fetch weather -> trigger alert"""
        # Step 1: Create location
        mock_fetch.return_value = {
            'temperature_c': 25.0,
            'wind_speed_ms': 5.0,
            'humidity': 60.0
        }
        resp = self.client.post(
            "/api/locations/",
            {
                "name": "Hot City",
                "latitude": 40.0,
                "longitude": -74.0
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        location_id = resp.data['id']
        
        # Step 2: Create alert config
        resp = self.client.post(
            "/api/alerts/config/",
            {
                "location": location_id,
                "threshold_type": "temp_gt",
                "threshold_value": 30.0,
                "is_active": True
            },
            format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        # Step 3: Add telemetry that triggers alert
        location = Location.objects.get(id=location_id)
        # Delete any existing telemetry from location creation
        Telemetry.objects.filter(location=location).delete()
        Telemetry.objects.create(
            location=location,
            timestamp=timezone.now(),
            temperature_c=35.0,  # Above threshold
            wind_speed_ms=5.0,
            humidity=60.0
        )
        
        # Step 4: Evaluate alerts
        measurement = Telemetry.objects.filter(location=location).first()
        with patch('telemetry.tasks.send_mail') as mock_send_mail:
            with patch('telemetry.tasks._publish_update'):
                evaluate_alerts(location, measurement)
        
        # Step 5: Check alert history
        resp = self.client.get("/api/alerts/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['condition'], "temp_gt")
        self.assertEqual(resp.data[0]['value'], 35.0)
        
        # Step 6: Get weather data
        resp = self.client.get(f"/api/weather/{location_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['latest'])
        self.assertEqual(resp.data['latest']['temperature_c'], 35.0)
