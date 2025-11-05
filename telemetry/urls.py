from django.urls import path
from .views import LocationListCreate, WeatherByLocation, AlertConfigCreate, AlertHistoryList

urlpatterns = [
    path('locations/', LocationListCreate.as_view()),
    path('weather/<int:location_id>/', WeatherByLocation.as_view()),
    path('alerts/config/', AlertConfigCreate.as_view()),
    path('alerts/history/', AlertHistoryList.as_view())

]