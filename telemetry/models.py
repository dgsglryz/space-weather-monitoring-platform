from django.db import models
from django.conf import settings


class Location(models.Model):
    name = models.CharField(max_length=120)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    added_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations"
    )

    def __str__(self):
        return self.name


class Telemetry(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="telemetry")
    timestamp = models.DateTimeField(db_index=True)
    temperature_c = models.FloatField(null=True, blank=True)
    wind_speed_ms = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('location', 'timestamp')
        indexes = [
            models.Index(fields=['location', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.location.name} @ {self.timestamp}"


class AlertConfig(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_configs")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="alert_configs")
    threshold_type = models.CharField(max_length=16)
    threshold_value = models.FloatField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.location.name} - {self.threshold_type} {self.threshold_value} ({status})"


class AlertHistory(models.Model):
    triggered_at = models.DateTimeField(auto_now_add=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="alert_history")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_history")
    condition = models.CharField(max_length=16)
    value = models.FloatField()
    user_notified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.location.name} - {self.condition}={self.value} @ {self.triggered_at}"


class GeocodeCache(models.Model):
    city_name = models.CharField(max_length=200, unique=True, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.city_name} - {self.latitude}, {self.longitude}'
