from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from telemetry.views import DashboardView, LocationPageView, delete_location
from django.views.generic.base import RedirectView
from telemetry.views_ssr import AlertConfigView, AlertConfigToggleView, AlertConfigDeleteView, AlertHistoryView


urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/auth/token/', TokenObtainPairView.as_view()),
    path('api/auth/token/refresh/', TokenRefreshView.as_view()),
    path('api/', include('telemetry.urls')),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('locations-page/', LocationPageView.as_view(), name='locations-page'),
    path('locations-page/delete/<int:pk>/delete/', delete_location.as_view(), name='delete-location'),
    path('alerts-config/',AlertConfigView.as_view(),name='alerts-config'),
    path('alerts-config/<int:pk>/toggle/',AlertConfigToggleView.as_view(),name='alerts-config-toggle'),
    path('alerts-config/<int:pk>/delete/',AlertConfigDeleteView.as_view(),name='alerts-config-delete'),
    path('alerts-history/',AlertHistoryView.as_view(),name='alerts-history')
]
