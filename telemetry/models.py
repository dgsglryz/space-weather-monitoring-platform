from django.db import models
from django.conf import settings


# Create your models here.
class Location(models.Model):
    name=models.CharField(max_length=120)
    latitude=models.FloatField(null=True, blank=True)
    longitude=models.FloatField(null=True, blank=True)
    added_by_user=models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations"
    )

class Telemetry(models.Model):
    location=models.ForeignKey(Location, on_delete=models.CASCADE, related_name="telemetry")
    timestamp=models.DateTimeField(db_index=True)
    kp_index=models.FloatField(null=True, blank=True)
    bz_nT=models.FloatField(null=True, blank=True)
    solar_wind_kms=models.FloatField(null=True, blank=True)

class AlertConfig(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_configs")
    location=models.ForeignKey(Location, on_delete=models.CASCADE, related_name="alert_configs")
    threshold_type=models.CharField(max_length=16)
    threshold_value=models.FloatField()
    is_active=models.BooleanField(default=True)

class AlertHistory(models.Model):
    triggered_at=models.DateTimeField(auto_now_add=True)
    location=models.ForeignKey(Location, on_delete=models.CASCADE, related_name="alert_history")
    condition=models.CharField(max_length=16)
    value=models.FloatField()
    user_notified=models.BooleanField(default=False)




