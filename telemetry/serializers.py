from rest_framework import serializers
from .models import Location, Telemetry, AlertConfig, AlertHistory


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ('id','name','latitude', 'longitude')


class TelemetrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Telemetry
        fields = ('timestamp','temperature_c','wind_speed_ms','humidity')


class AlertConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertConfig
        fields = ('location','threshold_type','threshold_value','is_active')


class AlertHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertHistory
        fields = ('triggered_at','condition','value','location')
