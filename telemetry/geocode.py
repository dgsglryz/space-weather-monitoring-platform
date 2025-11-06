import os
import requests, time
from django.conf import settings
from django.db import transaction
from .models import GeocodeCache


def _normalize(city: str):
    return (city or '').strip().lower()


def _cache_get(city):
    key = _normalize(city)
    row = GeocodeCache.objects.filter(city_name=key).first()
    if row:
        return (row.latitude, row.longitude)
    
    return None


@transaction.atomic
def _cache_set(city,lat,lon):
    key = _normalize(city)
    GeocodeCache.objects.update_or_create(city_name=key,
    defaults={
        'latitude':float(lat),'longitude':float(lon)
    })


def _provider_owm(city):
    key=getattr(settings,'OWM_API_KEY','') or os.getenv('OWM_API_KEY','')
    if not key:
        return None

    url = "https://api.openweathermap.org/geo/1.0/direct"
    params={'q':city,'limit':1,'appid':key}
    response = requests.get(url,params=params,timeout=10)
    response.raise_for_status()
    data = response.json()
    
    if not data:
        return None

    return float(data[0]['lat']),float(data[0]['lon'])


def _provider_openmeteo(city):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params={'name':city,'count':1}
    response = requests.get(url,params=params,headers={'User-Agent':'space-weather-monitor'},timeout=10)
    response.raise_for_status()

    data = response.json() or {}
    results = data.get('results') or []
    if not results:
        return None

    top = results[0]
    return float(top['latitude']),float(top['longitude'])


def geocode_city(city,sleep_seconds=0.0):
    city_norm = _normalize(city)
    if not city_norm:
        return None

    cached = _cache_get(city_norm)
    if cached:
        return cached

    try:
        coords = _provider_owm(city_norm)
        if coords:
            _cache_set(city_norm,*coords)

            if sleep_seconds>0:
                time.sleep(sleep_seconds)
            return coords
    except Exception:
        pass

    try:
        coords = _provider_openmeteo(city_norm)
        if coords:
            _cache_set(city_norm,*coords)

            if sleep_seconds>0:
                time.sleep(sleep_seconds)
            return coords
    except Exception:
        pass

    if sleep_seconds>0:
        time.sleep(sleep_seconds)
    return None

