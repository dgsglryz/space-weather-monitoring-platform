from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.db.models import Max
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .serializers import LocationSerializer, AlertConfigSerializer, AlertHistorySerializer
from .permissions import IsAdminOrOwner
from .geocode import geocode_city
from .owm_client import fetch_current_by_coords
from django.core.cache import cache


class LocationListCreate(ListCreateAPIView):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Location.objects.filter(added_by_user=self.request.user)

    def perform_create(self, serializer):
        location = serializer.save(added_by_user=self.request.user)
        if location.latitude and location.longitude:
            try:
                data = fetch_current_by_coords(location.latitude, location.longitude)
                if data:
                    timestamp = timezone.now().replace(second=0, microsecond=0)
                    Telemetry.objects.create(
                        location=location,
                        timestamp=timestamp,
                        temperature_c=data.get('temperature_c'),
                        wind_speed_ms=data.get('wind_speed_ms'),
                        humidity=data.get('humidity')
                    )
            except Exception:
                pass


class WeatherByLocation(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, location_id):
        location = get_object_or_404(Location, id=location_id, added_by_user=request.user)
        try:
            hours = int(request.query_params.get('hours',24))
        except ValueError:
            hours = 24

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

        series = []
        for x in qs:
            series.append({
                'timestamp': x.timestamp.isoformat(),
                'temperature_c': x.temperature_c,
                'wind_speed_ms': x.wind_speed_ms,
                'humidity': x.humidity
            })

        response_data = {
            'location': LocationSerializer(location).data,
            'latest': latest_data,
            'series': series
        }

        cache.set(cache_key, response_data, timeout=30)

        return Response(response_data)


class AlertConfigCreate(APIView):
    permission_classes = [IsAuthenticated]

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
    
    def get(self, request):
        qs = AlertHistory.objects.filter(user=request.user)
        serializer = AlertHistorySerializer(qs, many=True)
        return Response(serializer.data)


@method_decorator(login_required, name='dispatch')
class LocationPageView(APIView):
    template_name = 'locations.html'

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
        except Exception:
            messages.error(request, "Geocoding failed. Please provide coordinates.")
            return redirect('locations-page')

        location = Location.objects.create(
            name=name,
            latitude=latitude,
            longitude=longitude,
            added_by_user=request.user
        )
        try:
            data = fetch_current_by_coords(latitude, longitude)
            if data:
                timestamp = timezone.now().replace(second=0, microsecond=0)
                Telemetry.objects.create(
                    location=location,
                    timestamp=timestamp,
                    temperature_c=data.get('temperature_c'),
                    wind_speed_ms=data.get('wind_speed_ms'),
                    humidity=data.get('humidity')
                )
        except Exception:
            pass
        
        messages.success(request, f"Location '{name}' added.")
        return redirect('locations-page')


@method_decorator(login_required, name='dispatch')
class delete_location(APIView):
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

        try:
            val = float(thr_value)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid threshold value')
            return redirect('alerts-config')

        AlertConfig.objects.create(
            user=request.user,
            location=loc,
            threshold_type=thr_type,
            threshold_value=val,
            is_active=is_active
        )
        messages.success(request, 'Alert configuration saved')
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
            for item in latest_times:
                loc_id = item['location_id']
                latest = Telemetry.objects.filter(location_id=loc_id, timestamp=item['max_time']).first()
                if latest:
                    latest_telemetry[loc_id] = latest

        for loc in locs:
            latest = latest_telemetry.get(loc.id)
            status = self._status_for(loc, latest)
            cards.append({'loc': loc, 'latest': latest, 'status': status})

        first_id = locs.first().id if locs.exists() else None
        series = []
        if first_id:
            since = timezone.now() - timedelta(hours=24)
            telemetry = Telemetry.objects.filter(location_id=first_id, timestamp__gte=since).order_by('timestamp')
            for x in telemetry:
                series.append({
                    'timestamp': x.timestamp.isoformat(),
                    'temperature_c': x.temperature_c,
                    'wind_speed_ms': x.wind_speed_ms,
                    'humidity': x.humidity
                })

        return render(request, self.template_name, {
            'locations': locs,
            'cards': cards, 
            'first_location_id': first_id,
            'series_json': series
        })

    def _status_for(self, loc, latest):
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
        
        if latest.temperature_c is not None and latest.temperature_c < 5:
            return 'warning'
        if latest.wind_speed_ms is not None and latest.wind_speed_ms > 8:
            return 'warning'
            
        return 'normal'
