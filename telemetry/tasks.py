from celery import shared_task
from django.utils import timezone
from django.db import transaction
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .owm_client import fetch_current_by_coords

@shared_task
def fetch_and_store_weather():
    now = timezone.now()
    for loc in Location.objects.all():
        if loc.latitude is None or loc.longitude is None:
            continue

        data = fetch_current_by_coords(loc.latitude, loc.longitude)
        with transaction.atomic():
            measurement = Telemetry.objects.create(location=loc, timestamp=now, 
            temperature_c=data['temperature_c'],
            wind_speed_ms=data['wind_speed_ms'],
            humidity=data['humidity'])
            evaluate_alerts(loc, measurement)
            
def _value_for_threshold(threshold_type: str, m: Telemetry):
    if threshold_type.startswith('temp'):
        return m.temperature_c
    if threshold_type.startswith('wind'):
        return m.wind_speed_ms
    if threshold_type.startswith('humidity'):
        return m.humidity
    return None

def evaluate_alerts(location: Location, measurement: Telemetry):
    configs = AlertConfig.objects.filter(location=location, is_active=True)

    for cfg in configs:
        val = _value_for_threshold(cfg.threshold_type, measurement)
        if val is None:
            continue

        ok = False
        t = cfg.threshold_type
        if t.endswith('_gt'):
            ok = val > cfg.threshold_value
        elif t.endswith('_lt'):
            ok = val < cfg.threshold_value

        if ok:
            AlertHistory.objects.create(location=location, 
             condition=cfg.threshold_type,value=val,user_notified=False)

