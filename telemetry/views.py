from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404,render
from django.utils import timezone
from datetime import timedelta
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .serializers import LocationSerializer, TelemetrySerializer, AlertConfigSerializer, AlertHistorySerializer
from .permissions import IsAdminOrOwner
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.shortcuts import redirect
from .geocode import geocode_city
from django.views import View

class LocationListCreate(ListCreateAPIView):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Location.objects.filter(added_by_user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(added_by_user=self.request.user)

class WeatherByLocation(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, location_id):
        location = get_object_or_404(Location, id=location_id, added_by_user=request.user)
        try:
            hours = int(request.GET.get('hours',24))
        except ValueError:
            hours = 24
        since = timezone.now() - timedelta(hours=hours)
        qs = Telemetry.objects.filter(location=location, timestamp__gte=since).order_by('timestamp')
        latest = qs.last()
        
        def row(x):
            return {
                'timestamp': x.timestamp.isoformat(),
                'temperature_c': x.temperature_c,
                'wind_speed_ms': x.wind_speed_ms,
                'humidity': x.humidity
            }

        return Response({
            'location': LocationSerializer(location).data,
            'latest': row(latest) if latest else None,
            'series': [row(x) for x in qs]
        })

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
        qs = AlertHistory.objects.filter(location__added_by_user=request.user)
        serializer = AlertHistorySerializer(qs, many=True)
        return Response(serializer.data)

@method_decorator(login_required, name='dispatch')
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        locs = Location.objects.filter(added_by_user=request.user).order_by('name')
        first_id = locs[0].id if locs else None
        return render(request,'dashboard.html',{
            'locations': locs,
            'first_location_id': first_id,
        })


@method_decorator(login_required, name='dispatch')
class LocationPageView(APIView):
    template_name = 'locations.html'

    def get(self, request):
        qs = Location.objects.filter(added_by_user=request.user).order_by('name')
        return render(request, self.template_name, {'locations': qs})

    def post(self, request):
        name = (request.POST.get('name') or '').strip()
        lat = (request.POST.get('latitude') or '').strip()
        lon = (request.POST.get('longitude') or '').strip()

        if not name:
            messages.error(request, "City name is required.")
            return redirect('locations-page')

        try:
            if lat and lon:
                latitude = float(lat)
                longitude = float(lon)
            else:
                latitude, longitude = geocode_city(name)
        except Exception:
            messages.error(request, "Geocoding failed. Please provide coordinates.")
            return redirect('locations-page')

        Location.objects.create(
            name=name, latitude=latitude, longitude=longitude,
            added_by_user=request.user
        )
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

    





