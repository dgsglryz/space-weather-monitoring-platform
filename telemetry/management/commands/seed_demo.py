from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from telemetry.models import AlertConfig, Location, Telemetry


class Command(BaseCommand):
    help = "Seed demo data with a demo user, locations, and recent telemetry."  # noqa: D401

    DEMO_EMAIL = "demo@example.com"
    DEMO_PASSWORD = "ChangeMe123!"
    LOCATIONS = [
        ("Toronto Ground Station", 43.65107, -79.347015),
        ("Tokyo Tracking Hub", 35.6762, 139.6503),
        ("Sydney Uplink", -33.8688, 151.2093),
    ]

    def handle(self, *args, **options):
        User = get_user_model()

        user, _created = User.objects.get_or_create(
            username=self.DEMO_EMAIL,
            defaults={
                "email": self.DEMO_EMAIL,
            },
        )
        if not user.has_usable_password():
            user.set_password(self.DEMO_PASSWORD)
            user.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS(f"Demo user: {self.DEMO_EMAIL} / {self.DEMO_PASSWORD}"))

        now = timezone.now().replace(minute=0, second=0, microsecond=0)

        for name, lat, lon in self.LOCATIONS:
            location, _ = Location.objects.get_or_create(
                name=name,
                defaults={
                    "latitude": lat,
                    "longitude": lon,
                    "added_by_user": user,
                },
            )

            if location.added_by_user_id != user.id:
                location.added_by_user = user
                location.latitude = lat
                location.longitude = lon
                location.save()

            readings = []
            for i in range(48):
                timestamp = now - timedelta(minutes=30 * i)
                readings.append(
                    Telemetry(
                        location=location,
                        timestamp=timestamp,
                        temperature_c=15 + (i % 6) * 1.5,
                        wind_speed_ms=3 + (i % 4),
                        humidity=55 + (i % 5) * 2,
                    )
                )

            Telemetry.objects.bulk_create(readings, ignore_conflicts=True)

            AlertConfig.objects.get_or_create(
                user=user,
                location=location,
                threshold_type="temp_gt",
                defaults={
                    "threshold_value": 30.0,
                    "is_active": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("Demo locations and telemetry seeded."))

