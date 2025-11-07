import os
import requests
import time
from django.conf import settings
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
    key = getattr(settings, 'OWM_API_KEY', '') or os.getenv('OWM_API_KEY', '')
    if not key:
        return None

    try:
        url = "https://api.openweathermap.org/geo/1.0/direct"
        params = {'q': city, 'limit': 1, 'appid': key}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None

        return float(data[0]['lat']), float(data[0]['lon'])
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None


def _provider_openmeteo(city):
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {'name': city, 'count': 1}
        response = requests.get(url, params=params, headers={'User-Agent': 'space-weather-monitor'}, timeout=10)
        response.raise_for_status()

        data = response.json() or {}
        results = data.get('results') or []
        if not results:
            return None

        top = results[0]
        return float(top['latitude']), float(top['longitude'])
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None


def geocode_city(city, sleep_seconds=0.0):
    city_norm = _normalize(city)
    if not city_norm:
        return None

    cached = _cache_get(city_norm)
    if cached:
        return cached

    try:
        coords = _provider_owm(city_norm)
        if coords:
            _cache_set(city_norm, *coords)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords
    except Exception as e:
        logger.debug(f"OWM geocoding provider failed for '{city_norm}': {e}")

    try:
        coords = _provider_openmeteo(city_norm)
        if coords:
            _cache_set(city_norm, *coords)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            return coords
    except Exception as e:
        logger.debug(f"OpenMeteo geocoding provider failed for '{city_norm}': {e}")

    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return None

