import os
import requests
from django.conf import settings


def fetch_current_by_coords(latitude, longitude):
    key = getattr(settings, "OWM_API_KEY", "") or os.getenv("OWM_API_KEY", "")
    if not key:
        raise RuntimeError("OWM_API_KEY missing")

    url = 'https://api.openweathermap.org/data/2.5/weather'
    params = {
        'lat': latitude,
        'lon': longitude,
        'appid': key,
        'units': 'metric',
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    main = data.get('main', {})
    wind = data.get('wind', {})
    
    temp = main.get('temp')
    wind_speed = wind.get('speed')
    hum = main.get('humidity')
    
    return {
        'temperature_c': float(temp) if temp is not None else None,
        'wind_speed_ms': float(wind_speed) if wind_speed is not None else None,
        'humidity': float(hum) if hum is not None else None,
    }

