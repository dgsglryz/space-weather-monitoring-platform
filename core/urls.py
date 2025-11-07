from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.views.generic.base import RedirectView
from telemetry.views import (
    LocationPageView, DeleteLocationView, DashboardView,
    AlertConfigView, AlertConfigToggleView, AlertConfigDeleteView, AlertHistoryView
)
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/auth/token/', TokenObtainPairView.as_view()),
    path('api/auth/token/refresh/', TokenRefreshView.as_view()),
    path('api/', include('telemetry.urls')),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('locations-page/', LocationPageView.as_view(), name='locations-page'),
    path('locations-page/delete/<int:pk>/delete/', DeleteLocationView.as_view(), name='delete-location'),
    path('alerts-config/',AlertConfigView.as_view(),name='alerts-config'),
    path('alerts-config/<int:pk>/toggle/',AlertConfigToggleView.as_view(),name='alerts-config-toggle'),
    path('alerts-config/<int:pk>/delete/',AlertConfigDeleteView.as_view(),name='alerts-config-delete'),
    path('alerts-history/',AlertHistoryView.as_view(),name='alerts-history'),
    path('api/schema/',SpectacularAPIView.as_view(),name='schema'),
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'),name='docs'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
