import os
import requests
from django.conf import settings

def geocode_city_owm(city_name: str):

    key = getattr(settings, 'OWM_API_KEY', '') or os.getenv('OWM_API_KEY', '')
    if not key:
        raise ValueError("OWM_API_KEY missing")

    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {
        'q': city_name,
        'limit': 1,
        'appid': key,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    if not data:
        return None
    
    return float(data[0]['lat']), float(data[0]['lon'])
    


