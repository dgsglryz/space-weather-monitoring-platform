from django.contrib import admin
from .models import Location, Telemetry, AlertConfig, AlertHistory
from .geocode import geocode_city_owm

# Register your models here.
@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display=("name","latitude","longitude","added_by_user")
    readonly_fields=('latitude','longitude')

    def save_model(self, request, obj, form, change):
        if not obj.latitude or not obj.longitude:
            coords = geocode_city_owm(obj.name)
            if coords:
                obj.latitude, obj.longitude = coords

        if not obj.added_by_user:
            obj.added_by_user = request.user
        super().save_model(request, obj, form, change)



admin.site.register(Telemetry)
admin.site.register(AlertConfig)
admin.site.register(AlertHistory)   

