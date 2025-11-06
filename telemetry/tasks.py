from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .owm_client import fetch_current_by_coords


@shared_task
def fetch_and_store_weather():
    base_time = timezone.now()
    base_time = base_time.replace(second=0, microsecond=0)
    
    locations = Location.objects.filter(latitude__isnull=False, longitude__isnull=False)
    
    for idx, loc in enumerate(locations):
        try:
            data = fetch_current_by_coords(loc.latitude, loc.longitude)
            
            if data is None:
                continue
            
            timestamp = base_time + timedelta(seconds=idx)
            
            measurement, created = Telemetry.objects.get_or_create(
                location=loc,
                timestamp=timestamp,
                defaults={
                    'temperature_c': data.get('temperature_c'),
                    'wind_speed_ms': data.get('wind_speed_ms'),
                    'humidity': data.get('humidity')
                }
            )
            
            if created:
                evaluate_alerts(loc, measurement)
        except Exception as e:
            print(f"Error fetching weather for {loc.name}: {e}")
            continue


def evaluate_alerts(location, measurement):
    configs = AlertConfig.objects.filter(location=location, is_active=True)

    for cfg in configs:
        val = None
        if cfg.threshold_type.startswith('temp'):
            val = measurement.temperature_c
        elif cfg.threshold_type.startswith('wind'):
            val = measurement.wind_speed_ms
        elif cfg.threshold_type.startswith('humidity'):
            val = measurement.humidity
        
        if val is None:
            continue

        should_alert = False
        t = cfg.threshold_type
        if t.endswith('_gt') and val > cfg.threshold_value:
            should_alert = True
        elif t.endswith('_lt') and val < cfg.threshold_value:
            should_alert = True
        
        if should_alert:
            AlertHistory.objects.create(
                location=location,
                user=cfg.user,
                condition=cfg.threshold_type,
                value=val,
                user_notified=False
            )
