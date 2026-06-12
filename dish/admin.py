from django.contrib import admin
from .models import TelemetryReading, Event, WatchdogConfig


@admin.register(TelemetryReading)
class TelemetryReadingAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "gps_valid", "gps_sats", "gps_inhibited", "pop_ping_latency_ms", "uptime_s"]
    list_filter = ["gps_valid", "gps_inhibited"]
    readonly_fields = ["timestamp", "raw_json"]
    ordering = ["-timestamp"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "event_type", "source", "actor"]
    list_filter = ["event_type", "source"]
    readonly_fields = ["timestamp", "detail"]
    ordering = ["-timestamp"]


@admin.register(WatchdogConfig)
class WatchdogConfigAdmin(admin.ModelAdmin):
    list_display = ["mode", "poll_interval_s", "deny_debounce_s", "recover_debounce_s", "last_poll_at", "updated_at"]

    def has_add_permission(self, request):
        return not WatchdogConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
