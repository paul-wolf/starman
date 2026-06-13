from django.db import models
from django.utils import timezone


class TelemetryReading(models.Model):
    timestamp = models.DateTimeField(db_index=True, default=timezone.now)
    gps_valid = models.BooleanField(default=False)
    gps_sats = models.IntegerField(default=0)
    gps_inhibited = models.BooleanField(default=False)
    pnt_filter_state = models.CharField(max_length=64, default="")
    pop_ping_latency_ms = models.FloatField(null=True)
    pop_ping_drop_rate = models.FloatField(default=0)
    downlink_bps = models.FloatField(null=True)
    uplink_bps = models.FloatField(null=True)
    fraction_obstructed = models.FloatField(null=True)
    attitude_uncertainty_deg = models.FloatField(null=True)
    attitude_state = models.CharField(max_length=64, default="")
    uptime_s = models.BigIntegerField(default=0)
    software_version = models.CharField(max_length=128, default="")
    country_code = models.CharField(max_length=8, default="")
    disablement_code = models.CharField(max_length=64, default="")
    outage_cause = models.CharField(max_length=64, null=True)
    mobility_class = models.CharField(max_length=64, default="")
    is_snr_above_noise_floor = models.BooleanField(null=True)
    connectivity_ok = models.BooleanField(null=True)
    raw_json = models.JSONField(default=dict)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"TelemetryReading @ {self.timestamp}"


class Event(models.Model):
    class EventType(models.TextChoices):
        GPS_DENIED = "GPS_DENIED"
        GPS_RECOVERED = "GPS_RECOVERED"
        INHIBIT_SET = "INHIBIT_SET"
        INHIBIT_CLEARED = "INHIBIT_CLEARED"
        OUTAGE_START = "OUTAGE_START"
        OUTAGE_END = "OUTAGE_END"
        NET_OUTAGE_START = "NET_OUTAGE_START"
        NET_OUTAGE_END = "NET_OUTAGE_END"
        REBOOT_DETECTED = "REBOOT_DETECTED"
        DISH_UNREACHABLE = "DISH_UNREACHABLE"
        CONTROL_ACTION = "CONTROL_ACTION"
        WATCHDOG_MODE_CHANGED = "WATCHDOG_MODE_CHANGED"

    class Source(models.TextChoices):
        WATCHDOG = "WATCHDOG"
        USER = "USER"
        SYSTEM = "SYSTEM"

    timestamp = models.DateTimeField(db_index=True, default=timezone.now)
    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    source = models.CharField(max_length=16, choices=Source.choices)
    actor = models.CharField(max_length=150, null=True)
    detail = models.JSONField(default=dict)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.event_type} [{self.source}] @ {self.timestamp}"


class WatchdogConfig(models.Model):
    class Mode(models.TextChoices):
        LOG_ONLY = "LOG_ONLY"
        MONITOR = "MONITOR"
        ENFORCE = "ENFORCE"

    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.LOG_ONLY)
    poll_interval_s = models.IntegerField(default=10)
    deny_debounce_s = models.IntegerField(default=90)
    recover_debounce_s = models.IntegerField(default=120)
    min_sats_for_good = models.IntegerField(default=5)
    boot_warmup_s = models.IntegerField(default=300)
    probe_hosts = models.TextField(default="8.8.8.8,1.1.1.1")
    manual_override_until = models.DateTimeField(null=True, blank=True)
    last_poll_at = models.DateTimeField(null=True, blank=True)
    last_retain_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Watchdog Config"
        verbose_name_plural = "Watchdog Config"

    def __str__(self):
        return f"WatchdogConfig (mode={self.mode})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
