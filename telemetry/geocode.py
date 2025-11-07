import os
import requests
import time
from django.conf import settings
from django.db import DatabaseError, IntegrityError
from .models import GeocodeCache
import logging

logger = logging.getLogger(__name__)


def _normalize(city):
    return (city or '').strip().lower()


def _cache_get(city):
    key = _normalize(city)
    row = GeocodeCache.objects.filter(city_name=key).first()
    if row:
        return (row.latitude, row.longitude)
    
    return None


def _cache_set(city, lat, lon):
    key = _normalize(city)
    GeocodeCache.objects.update_or_create(
        city_name=key,
        defaults={
            'latitude': float(lat),
            'longitude': float(lon)
        }
    )


def _provider_owm(city):
    """Geocode city using OpenWeatherMap API.
    
    Returns (latitude, longitude) tuple on success, None on failure.
    Logs failures for observability.
    """
    key = getattr(settings, 'OWM_API_KEY', '') or os.getenv('OWM_API_KEY', '')
    if not key:
        logger.debug(f"OWM API key missing, skipping geocode for '{city}'")
        return None

    try:
        url = "https://api.openweathermap.org/geo/1.0/direct"
        params = {'q': city, 'limit': 1, 'appid': key}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            logger.debug(f"OWM geocoding returned empty results for '{city}'")
            return None

        return float(data[0]['lat']), float(data[0]['lon'])
    except requests.RequestException as e:
        logger.warning(f"OWM geocoding request failed for '{city}': {e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        logger.warning(f"OWM geocoding data parsing failed for '{city}': {e}")
        return None


def _provider_openmeteo(city):
    """Geocode city using OpenMeteo API.
    
    Returns (latitude, longitude) tuple on success, None on failure.
    Logs failures for observability.
    """
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {'name': city, 'count': 1}
        response = requests.get(url, params=params, headers={'User-Agent': 'space-weather-monitor'}, timeout=10)
        response.raise_for_status()

        data = response.json() or {}
        results = data.get('results') or []
        if not results:
            logger.debug(f"OpenMeteo geocoding returned empty results for '{city}'")
            return None

        top = results[0]
        return float(top['latitude']), float(top['longitude'])
    except requests.RequestException as e:
        logger.warning(f"OpenMeteo geocoding request failed for '{city}': {e}")
        return None
    except (KeyError, ValueError, IndexError) as e:
        logger.warning(f"OpenMeteo geocoding data parsing failed for '{city}': {e}")
        return None


def geocode_city(city, sleep_seconds=0.0):
    """Geocode city name to coordinates with provider fallback.
    
    Tries OWM first, falls back to OpenMeteo. Returns (lat, lon) tuple
    or None if all providers fail. Caches successful results.
    """
    city_norm = _normalize(city)
    if not city_norm:
        return None

    cached = _cache_get(city_norm)
    if cached:
        return cached

    # Try OWM provider first
    coords = _provider_owm(city_norm)
    if coords:
        try:
            _cache_set(city_norm, *coords)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords
        except (DatabaseError, IntegrityError, ValueError) as e:
            logger.warning(f"Failed to cache OWM geocode result for '{city_norm}': {e}")
            # Return coords anyway even if cache fails
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords

    # Fall back to OpenMeteo provider
    coords = _provider_openmeteo(city_norm)
    if coords:
        try:
            _cache_set(city_norm, *coords)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords
        except (DatabaseError, IntegrityError, ValueError) as e:
            logger.warning(f"Failed to cache OpenMeteo geocode result for '{city_norm}': {e}")
            # Return coords anyway even if cache fails
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return None

