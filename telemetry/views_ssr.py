from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Location, AlertConfig, AlertHistory, Telemetry
from django.utils import timezone
from datetime import timedelta


class AlertConfigView(LoginRequiredMixin,View):
    template_name = 'alerts_config.html'
    
    def get(self, request):
        locations = Location.objects.filter(added_by_user=request.user)
        configs = AlertConfig.objects.filter(user=request.user).select_related('location').order_by('location__name')
        return render(request, self.template_name, {'locations': locations, 'configs':configs})

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

        messages.success(request, 'Alert configuration saved successfully')
        return redirect('alerts-config')


class AlertConfigToggleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cfg = get_object_or_404(AlertConfig, id=pk, user=request.user)
        cfg.is_active = not cfg.is_active
        cfg.save()
        messages.success(request, 'Alert configuration toggled successfully')
        return redirect('alerts-config')


class AlertConfigDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cfg = get_object_or_404(AlertConfig, id=pk, user=request.user)
        cfg.delete()
        messages.success(request, 'Alert configuration deleted successfully')
        return redirect('alerts-config')


class AlertHistoryView(LoginRequiredMixin, View):
    template_name = 'alerts_history.html'

    def get(self, request):
        history = (AlertHistory.objects.filter(location__added_by_user=request.user).select_related('location').order_by('-triggered_at')[:200])
        return render(request, self.template_name, {'history': history})


class DashboardView(LoginRequiredMixin, View):
    template_name = 'dashboard.html'

    def get(self, request):
        locs = Location.objects.filter(added_by_user=request.user).order_by('name')
        cards = []

        for loc in locs:
            latest = Telemetry.objects.filter(location=loc).order_by('-timestamp').first()
            status = self._status_for(loc, latest)
            cards.append({'loc': loc, 'latest': latest, 'status': status})

        first_id = locs.first().id if locs.exists() else None
        hours=24
        since = timezone.now() - timedelta(hours=hours)
        series = []
        if first_id:
            telemetry = Telemetry.objects.filter(location_id=first_id, timestamp__gte=since).order_by('timestamp')
            series = [
                {'timestamp': x.timestamp.isoformat(), 
                'temperature_c': x.temperature_c, 
                'wind_speed_ms': x.wind_speed_ms, 
                'humidity': x.humidity} 
                for x in telemetry
            ]

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
            metric, op = cfg.threshold_type.split('_')
            val = None
            if metric == 'temp':
                val = latest.temperature_c
            elif metric == 'wind':
                val = latest.wind_speed_ms
            elif metric == 'humidity':
                val = latest.humidity
            if val is None:
                continue
            if (op == 'gt' and val > cfg.threshold_value) or (op == 'lt' and val < cfg.threshold_value):
                return 'alert'
        
        if latest.temperature_c is not None and latest.temperature_c < 5:
            return 'warning'
        elif latest.wind_speed_ms is not None and latest.wind_speed_ms > 8:
            return 'warning'
            
        return 'normal'