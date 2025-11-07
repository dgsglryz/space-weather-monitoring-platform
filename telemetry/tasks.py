from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .owm_client import fetch_current_by_coords
from django.core.mail import send_mail
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import DatabaseError, IntegrityError
import logging
import time
import requests

logger = logging.getLogger(__name__)

# Simple delay so we do not hit API limits
API_RATE_LIMIT_DELAY_SECONDS = 1.1


@shared_task
def fetch_and_store_weather():
    base_time = timezone.now()
    base_time = base_time.replace(second=0, microsecond=0)
    
    locations = Location.objects.filter(latitude__isnull=False, longitude__isnull=False)
    
    for idx, loc in enumerate(locations):
        # Small pause between requests
        if idx > 0:
            time.sleep(API_RATE_LIMIT_DELAY_SECONDS)
        
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
        except (requests.RequestException, RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to fetch weather data for location {loc.id} ({loc.name}): {e}")
            continue
        except (DatabaseError, IntegrityError) as e:
            logger.error(f"Database error while storing weather for location {loc.id} ({loc.name}): {e}")
            continue


def evaluate_alerts(location, measurement):
    """Trigger alert flow for the latest reading."""
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


def send_alert_email(cfg, location, val):
    """Send the alert email and report success."""

    recipient = getattr(settings, "ALERT_NOTIFICATION_EMAIL", None)
    if not recipient:
        recipient = cfg.user.email

    if not recipient:
        logger.warning(
            "No email recipient configured for alert belonging to %s", cfg.user.username
        )
        return False

    subject = f'[Weather Alert] {location.name} - {cfg.threshold_type} = {val}'
    body = (
        f'Location: {location.name}\n'
        f'Condition: {cfg.threshold_type}\n'
        f'Value: {val}\n'
        f'Threshold: {cfg.threshold_value}\n'
    )

    to = [recipient]
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    attempts = max(getattr(settings, "ALERT_EMAIL_MAX_ATTEMPTS", 1), 1)
    backoff = max(getattr(settings, "ALERT_EMAIL_RETRY_BACKOFF_SECONDS", 0.0), 0.0)

    for attempt in range(1, attempts + 1):
        try:
            sent_count = send_mail(subject, body, from_email, to, fail_silently=False)
            if sent_count == 0:
                logger.warning(
                    "send_mail returned 0 for alert email to %s at %s",
                    cfg.user.username,
                    location.name,
                )
                return False
            logger.debug(
                "Alert email sent successfully to %s for %s",
                cfg.user.username,
                location.name,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to send alert email to %s for location %s on attempt %s/%s: %s",
                cfg.user.username,
                location.name,
                attempt,
                attempts,
                e,
            )
            if attempt < attempts and backoff:
                time.sleep(backoff)

    return False

def _publish_update(user_id, payload):
    """Push websocket update; ignore soft failures."""
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f'user_{user_id}',
            {
                'type': 'weather_update',
                'data': payload
            }
        )
    except (ConnectionError, RuntimeError, AttributeError) as e:
        logger.warning(f"WebSocket publish failed for user {user_id}: {e}")
    except Exception as e:
        logger.debug(f"WebSocket publish failed for user {user_id}: {e}")
