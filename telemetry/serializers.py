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
    ALLOWED_THRESHOLD_TYPES = {
        'temp_gt',
        'temp_lt',
        'wind_gt',
        'wind_lt',
        'humidity_gt',
        'humidity_lt',
    }

    class Meta:
        model = AlertConfig
        fields = ('location','threshold_type','threshold_value','is_active')

    def validate_threshold_type(self, value):
        value_normalized = (value or '').lower()
        if value_normalized not in self.ALLOWED_THRESHOLD_TYPES:
            allowed = ', '.join(sorted(self.ALLOWED_THRESHOLD_TYPES))
            raise serializers.ValidationError(
                f"Invalid threshold_type '{value}'. Allowed values: {allowed}."
            )
        return value_normalized

    def validate_threshold_value(self, value):
        if value is None:
            raise serializers.ValidationError("threshold_value is required.")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("threshold_value must be numeric.")


class AlertHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertHistory
        fields = ('triggered_at','condition','value','location','user','user_notified')


class WeatherByLocationResponseSerializer(serializers.Serializer):
    location = LocationSerializer()
    latest = TelemetrySerializer(allow_null=True)
    series = TelemetrySerializer(many=True)
