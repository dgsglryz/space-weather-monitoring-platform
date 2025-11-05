import os
import requests
from django.conf import settings
from typing import Dict, Any

from requests.sessions import RequestsCookieJar

def _get_api_key()->str:
    key = getattr(settings,"OWM_API_KEY","") or os.getenv("OWM_API_KEY","")
    if not key:
        raise RuntimeError("OWM_API_KEY missing")
    return key

def fetch_current_by_coords(latitude: float, longitude: float)->Dict[str, Any]:
    key= _get_api_key()

    url = 'https://api.openweathermap.org/data/2.5/weather'

    params = {
        'lat': latitude,
        'lon': longitude,
        'appid': key,
        'units': 'metric',
    }

    response = requests.get(url, params=params,timeout=10)
    response.raise_for_status()
    data = response.json()

    temp = data.get('main',{}).get('temp')
    wind = data.get('wind',{}).get('speed')
    hum = data.get('main',{}).get('humidity')
    return {
        'temperature_c': float(temp) if temp is not None else None,
        'wind_speed_ms': float(wind) if wind is not None else None,
        'humidity': float(hum) if hum is not None else None,
    }

