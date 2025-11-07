from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .owm_client import fetch_current_by_coords
from django.core.mail import send_mail
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import time

logger = logging.getLogger(__name__)

# Rate limiting: sleep between API calls to avoid hitting rate limits
API_RATE_LIMIT_DELAY_SECONDS = 1.1


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
            logger.warning(f"Failed to fetch/store weather for location {loc.id} ({loc.name}): {e}")
            continue


def evaluate_alerts(location, measurement):
    configs = AlertConfig.objects.filter(location=location, is_active=True).select_related('user')

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
        
        alert_history = None
        if should_alert:
            alert_history = AlertHistory.objects.create(
                location=location,
                user=cfg.user,
                condition=cfg.threshold_type,
                value=val,
                user_notified=False
            )
            
            try:
                send_alert_email(cfg, location, val)
                alert_history.user_notified = True
                alert_history.save(update_fields=['user_notified'])
            except Exception as e:
                logger.error(f"Failed to send alert email to {cfg.user.username} for location {location.name}: {e}")

        _publish_update(cfg.user.id, {
            'location': location.id,
            'status': 'alert' if should_alert else 'normal',
            'latest': {
                "temperature_c": measurement.temperature_c,
                "wind_speed_ms": measurement.wind_speed_ms,
                "humidity": measurement.humidity,
            }
        })


def send_alert_email(cfg,location, val):
    subject = f'[Weather Alert] {location.name} - {cfg.threshold_type} = {val}'
    body = (
        f'Location: {location.name}\n'
        f'Condition: {cfg.threshold_type}\n'
        f'Value: {val}\n'
        f'Threshold: {cfg.threshold_value}\n'
    )

    to = [cfg.user.email] if getattr(cfg.user,'email',None) else []
    if to:
        send_mail(subject, body, None,to, fail_silently=True)

def _publish_update(user_id, payload):
    """Publish WebSocket update for real-time UI refresh.
    
    Non-critical operation; failures are logged but don't affect main flow.
    """
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'user_{user_id}',
            {
                'type': 'weather_update',
                'data': payload
            }
        )
    except Exception as e:
        logger.debug(f"WebSocket publish failed for user {user_id}: {e}")
