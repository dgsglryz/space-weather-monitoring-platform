from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.db.models import Max, Q
from django.db import DatabaseError, IntegrityError
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from django.core.cache import cache
import json
import logging
from typing import Dict, Optional
import requests
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .serializers import (
    LocationSerializer,
    AlertConfigSerializer,
    AlertHistorySerializer,
    WeatherByLocationResponseSerializer,
)
from .permissions import IsAdminOrOwner
from .geocode import geocode_city
from .owm_client import fetch_current_by_coords

logger = logging.getLogger(__name__)

# Constants for default values and thresholds
DEFAULT_WEATHER_HOURS = 24
MAX_WEATHER_HOURS = getattr(settings, "WEATHER_HISTORY_MAX_HOURS", 168)
CACHE_TIMEOUT_SECONDS = getattr(settings, "WEATHER_CACHE_SECONDS", 30)
REFRESH_COOLDOWN_SECONDS = getattr(settings, "DASHBOARD_REFRESH_COOLDOWN_SECONDS", 300)
REFRESH_MAX_AGE_SECONDS = getattr(settings, "DASHBOARD_REFRESH_MAX_AGE_SECONDS", 2700)
TEMPERATURE_WARNING_THRESHOLD = 5  # Celsius
WIND_SPEED_WARNING_THRESHOLD = 8  # m/s


def build_telemetry_series(telemetry_queryset):
    """Turn telemetry rows into chart-friendly dicts."""
    series = []
    for telemetry in telemetry_queryset:
        series.append({
            'timestamp': telemetry.timestamp.isoformat(),
            'temperature_c': telemetry.temperature_c,
            'wind_speed_ms': telemetry.wind_speed_ms,
            'humidity': telemetry.humidity
        })
    return series


def create_telemetry_from_weather_data(location, weather_data):
    """Persist a telemetry point from the latest API payload."""
    if not weather_data:
        return None
    
    timestamp = timezone.now().replace(second=0, microsecond=0)
    try:
        return Telemetry.objects.create(
            location=location,
            timestamp=timestamp,
            temperature_c=weather_data.get('temperature_c'),
            wind_speed_ms=weather_data.get('wind_speed_ms'),
            humidity=weather_data.get('humidity')
        )
    except (DatabaseError, IntegrityError, ValueError, TypeError) as exc:
        logger.warning(
            "Failed to create telemetry for location %s: %s",
            location.id,
            exc,
        )
        return None


def _summaries_from_queryset(qs):
    """Collect basic min/max/avg stats for a queryset."""
    stats: Dict[str, Optional[float]] = {
        'temp_min': None,
        'temp_max': None,
        'temp_avg': None,
        'wind_min': None,
        'wind_max': None,
        'wind_avg': None,
        'humidity_min': None,
        'humidity_max': None,
        'humidity_avg': None,
    }

    def summarize(values):
        filtered = [v for v in values if v is not None]
        if not filtered:
            return None
        total = sum(filtered)
        count = len(filtered)
        return min(filtered), max(filtered), total / count

    temp_stats = summarize([item.temperature_c for item in qs])
    if temp_stats:
        stats['temp_min'], stats['temp_max'], stats['temp_avg'] = temp_stats

    wind_stats = summarize([item.wind_speed_ms for item in qs])
    if wind_stats:
        stats['wind_min'], stats['wind_max'], stats['wind_avg'] = wind_stats

    humidity_stats = summarize([item.humidity for item in qs])
    if humidity_stats:
        stats['humidity_min'], stats['humidity_max'], stats['humidity_avg'] = humidity_stats

    return stats


class LocationListCreate(ListCreateAPIView):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Location.objects.filter(added_by_user=self.request.user)

    def perform_create(self, serializer):
        """Save a location and try to seed a first reading."""
        location = serializer.save(added_by_user=self.request.user)
        if location.latitude is not None and location.longitude is not None:
            try:
                data = fetch_current_by_coords(location.latitude, location.longitude)
                create_telemetry_from_weather_data(location, data)
            except (requests.RequestException, RuntimeError, ValueError, TypeError, DatabaseError, IntegrityError) as exc:
                logger.warning(
                    "Failed to seed weather for location %s: %s",
                    location.id,
                    exc,
                )


class WeatherByLocation(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='hours',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Number of hours (1-168) of telemetry history to include.',
            )
        ],
        responses={
            200: WeatherByLocationResponseSerializer,
            403: OpenApiResponse(description='User does not own the requested location.'),
            404: OpenApiResponse(description='Location not found.'),
        },
    )
    def get(self, request, location_id):
        """Return recent data for the location, using a short cache."""
        location = get_object_or_404(Location, id=location_id, added_by_user=request.user)
        try:
            hours = int(request.query_params.get('hours', DEFAULT_WEATHER_HOURS))
        except ValueError:
            hours = DEFAULT_WEATHER_HOURS
        hours = min(max(1, hours), MAX_WEATHER_HOURS)

        cache_key = f'weather:{request.user.id}:{location_id}:{hours}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)


        since = timezone.now() - timedelta(hours=hours)
        qs = Telemetry.objects.filter(location=location, timestamp__gte=since).order_by('timestamp')
        latest = qs.last()

        latest_data = None
        if latest:
            latest_data = {
                'timestamp': latest.timestamp.isoformat(),
                'temperature_c': latest.temperature_c,
                'wind_speed_ms': latest.wind_speed_ms,
                'humidity': latest.humidity
            }

        series = build_telemetry_series(qs)

        response_data = {
            'location': LocationSerializer(location).data,
            'latest': latest_data,
            'series': series
        }

        cache.set(cache_key, response_data, timeout=CACHE_TIMEOUT_SECONDS)

        return Response(response_data)


class AlertConfigCreate(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=AlertConfigSerializer,
        responses={
            201: AlertConfigSerializer,
            400: OpenApiResponse(description='Validation errors for alert configuration.'),
            403: OpenApiResponse(description='Attempt to configure alert for a location owned by another user.'),
        },
    )
    def post(self, request):
        serializer = AlertConfigSerializer(data=request.data)
        if serializer.is_valid():
            location = serializer.validated_data['location']

            if location.added_by_user != request.user:
                return Response({'error': 'Not your location'}, status=403)

            serializer.save(user=request.user)
            return Response(serializer.data, status=201)
        
        return Response(serializer.errors, status=400)


class AlertHistoryList(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrOwner]
    
    @extend_schema(
        responses={
            200: AlertHistorySerializer(many=True),
        }
    )
    def get(self, request):
        qs = AlertHistory.objects.filter(user=request.user)
        serializer = AlertHistorySerializer(qs, many=True)
        return Response(serializer.data)


@method_decorator(login_required, name='dispatch')
class LocationPageView(APIView):
    template_name = 'locations.html'
    schema = None

    def get(self, request):
        qs = Location.objects.filter(added_by_user=request.user).order_by('name')
        return render(request, self.template_name, {'locations': qs})

    def post(self, request):
        name = request.POST.get('name', '').strip()
        lat = request.POST.get('latitude', '').strip()
        lon = request.POST.get('longitude', '').strip()

        if not name:
            messages.error(request, "City name is required.")
            return redirect('locations-page')

        try:
            if lat and lon:
                latitude = float(lat)
                longitude = float(lon)
            else:
                coords = geocode_city(name)
                if not coords:
                    messages.error(request, "Geocoding failed. Please provide coordinates.")
                    return redirect('locations-page')
                latitude, longitude = coords
        except (ValueError, TypeError):
            messages.error(request, "Invalid coordinates. Please check your input.")
            return redirect('locations-page')
        except (RuntimeError, requests.RequestException, DatabaseError, IntegrityError) as exc:
            logger.warning(f"Geocoding failed for city '{name}': {exc}")
            messages.error(request, "Geocoding service hatası. Lütfen koordinat girin veya tekrar deneyin.")
            return redirect('locations-page')

        location = Location.objects.create(
            name=name,
            latitude=latitude,
            longitude=longitude,
            added_by_user=request.user
        )
        try:
            data = fetch_current_by_coords(latitude, longitude)
            create_telemetry_from_weather_data(location, data)
        except (requests.RequestException, RuntimeError, ValueError, TypeError, DatabaseError, IntegrityError) as exc:
            logger.warning(f"Failed to fetch weather for location {location.id}: {exc}")
        
        messages.success(request, f"Location '{name}' added.")
        return redirect('locations-page')


@method_decorator(login_required, name='dispatch')
class DeleteLocationView(APIView):
    schema = None
    def post(self, request, pk):
        loc = get_object_or_404(Location, pk=pk, added_by_user=request.user)
        name = loc.name
        loc.delete()
        messages.success(request, f'Location "{name}" deleted.')
        return redirect('locations-page')


class AlertConfigView(LoginRequiredMixin, View):
    template_name = 'alerts_config.html'
    
    def get(self, request):
        locations = Location.objects.filter(added_by_user=request.user)
        configs = AlertConfig.objects.filter(user=request.user).select_related('location').order_by('location__name')
        return render(request, self.template_name, {'locations': locations, 'configs': configs})

    def post(self, request):
        loc_id = request.POST.get('location')
        thr_type = request.POST.get('threshold_type')
        thr_value = request.POST.get('threshold_value')
        is_active = request.POST.get('is_active') == 'on'

        loc = get_object_or_404(Location, id=loc_id, added_by_user=request.user)
        serializer = AlertConfigSerializer(
            data={
                'location': loc.id,
                'threshold_type': thr_type,
                'threshold_value': thr_value,
                'is_active': is_active,
            }
        )

        if serializer.is_valid():
            serializer.save(user=request.user)
            messages.success(request, 'Alert configuration saved')
        else:
            error_text = '; '.join([f"{field}: {', '.join(vals)}" for field, vals in serializer.errors.items()])
            messages.error(request, f'Unable to save alert: {error_text}')

        return redirect('alerts-config')


class AlertConfigToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cfg = get_object_or_404(AlertConfig, id=pk, user=request.user)
        cfg.is_active = not cfg.is_active
        cfg.save()
        messages.success(request, 'Alert configuration toggled')
        return redirect('alerts-config')


class AlertConfigDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cfg = get_object_or_404(AlertConfig, id=pk, user=request.user)
        cfg.delete()
        messages.success(request, 'Alert configuration deleted')
        return redirect('alerts-config')


class AlertHistoryView(LoginRequiredMixin, View):
    template_name = 'alerts_history.html'

    def get(self, request):
        history = AlertHistory.objects.filter(
            user=request.user
        ).select_related('location').order_by('-triggered_at')[:200]
        return render(request, self.template_name, {'history': history})


class DashboardView(LoginRequiredMixin, View):
    template_name = 'dashboard.html'

    def get(self, request):
        locs = Location.objects.filter(added_by_user=request.user).order_by('name')
        cards = []

        location_ids = [loc.id for loc in locs]
        latest_telemetry = {}
        if location_ids:
            latest_times = Telemetry.objects.filter(location_id__in=location_ids).values('location_id').annotate(
                max_time=Max('timestamp')
            )
            location_timestamp_pairs = [(item['location_id'], item['max_time']) for item in latest_times]
            if location_timestamp_pairs:
                q_objects = Q()
                for loc_id, max_time in location_timestamp_pairs:
                    q_objects |= Q(location_id=loc_id, timestamp=max_time)
                latest_telemetry_objects = Telemetry.objects.filter(q_objects).select_related('location')
                latest_telemetry = {t.location_id: t for t in latest_telemetry_objects}

        for loc in locs:
            latest = latest_telemetry.get(loc.id)
            status = self._status_for(loc, latest)
            cards.append({'loc': loc, 'latest': latest, 'status': status})

        first_id = locs.first().id if locs.exists() else None
        series = []
        if first_id:
            since = timezone.now() - timedelta(hours=24)
            telemetry = Telemetry.objects.filter(location_id=first_id, timestamp__gte=since).order_by('timestamp')
            series = build_telemetry_series(telemetry)

        issue_since = timezone.now() - timedelta(hours=6)
        email_issue = AlertHistory.objects.filter(
            user=request.user,
            user_notified=False,
            triggered_at__gte=issue_since,
        ).exists()

        response = render(request, self.template_name, {
            'locations': locs,
            'cards': cards,
            'first_location_id': first_id,
            'series_json': series,
            'refresh_cooldown_seconds': REFRESH_COOLDOWN_SECONDS,
            'refresh_max_age_seconds': REFRESH_MAX_AGE_SECONDS,
            'email_issue': email_issue,
        })
        response['Cache-Control'] = f"private, max-age={int(REFRESH_MAX_AGE_SECONDS)}"
        return response

    def _status_for(self, loc, latest):
        """Pick the badge to show for a location card."""
        if not latest:
            return 'no data'
        
        active = AlertConfig.objects.filter(location=loc, user=self.request.user, is_active=True)
        for cfg in active:
            parts = cfg.threshold_type.split('_')
            if len(parts) != 2:
                continue
            metric, op = parts
            
            if metric == 'temp':
                val = latest.temperature_c
            elif metric == 'wind':
                val = latest.wind_speed_ms
            elif metric == 'humidity':
                val = latest.humidity
            else:
                continue
                
            if val is None:
                continue
                
            if op == 'gt' and val > cfg.threshold_value:
                return 'alert'
            if op == 'lt' and val < cfg.threshold_value:
                return 'alert'
        
        if latest.temperature_c is not None and latest.temperature_c < TEMPERATURE_WARNING_THRESHOLD:
            return 'warning'
        if latest.wind_speed_ms is not None and latest.wind_speed_ms > WIND_SPEED_WARNING_THRESHOLD:
            return 'warning'
            
        return 'normal'


class LocationHistoricalView(LoginRequiredMixin, View):
    template_name = 'location_historical.html'

    def get(self, request, pk):
        location = get_object_or_404(Location, pk=pk, added_by_user=request.user)
        hours = self._parse_hours(request.GET.get('hours', DEFAULT_WEATHER_HOURS))
        since = timezone.now() - timedelta(hours=hours)

        telemetry = Telemetry.objects.filter(
            location=location,
            timestamp__gte=since,
        ).order_by('timestamp')

        series = build_telemetry_series(telemetry)
        latest = telemetry.last()
        stats = _summaries_from_queryset(telemetry)

        context = {
            'location': location,
            'hours': hours,
            'series_json': json.dumps(series),
            'latest': latest,
            'stats': stats,
            'data_count': telemetry.count(),
        }

        return render(request, self.template_name, context)

    @staticmethod
    def _parse_hours(raw_value):
        try:
            hours = int(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_WEATHER_HOURS

        return min(168, max(1, hours))
