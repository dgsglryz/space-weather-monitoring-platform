from django.contrib import admin
from .models import Location, Telemetry, AlertConfig, AlertHistory

# Register your models here.
@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display=("name","added_by_user")

admin.site.register(Telemetry)
admin.site.register(AlertConfig)
admin.site.register(AlertHistory)   

