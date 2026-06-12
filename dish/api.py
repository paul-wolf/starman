from datetime import datetime, timedelta, timezone
from typing import List, Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Query
from ninja.errors import HttpError

from dish.models import Event, TelemetryReading, WatchdogConfig
from dish.schemas import (
    DishInfoOut,
    EventOut,
    GpsStateOut,
    TelemetryReadingOut,
    WatchdogConfigOut,
)

api = NinjaAPI(title="Starlink Console API", version="1.0")


# ── Status ────────────────────────────────────────────────────────────────────

@api.get("/status/live", response=TelemetryReadingOut)
def status_live(request: HttpRequest):
    reading = TelemetryReading.objects.order_by("-timestamp").first()
    if reading is None:
        raise HttpError(503, "No telemetry yet — is the watchdog running?")
    return reading


@api.get("/status/history", response=List[TelemetryReadingOut])
def status_history(
    request: HttpRequest,
    since: Optional[datetime] = Query(None, description="Start of window (ISO 8601); defaults to 1 hour ago"),
    until: Optional[datetime] = Query(None, description="End of window (ISO 8601); defaults to now"),
    limit: int = Query(500, description="Max data points returned (downsampled if needed)", ge=1, le=5000),
):
    now = datetime.now(tz=timezone.utc)
    since = since or (now - timedelta(hours=1))
    until = until or now

    qs = (
        TelemetryReading.objects
        .filter(timestamp__gte=since, timestamp__lte=until)
        .order_by("timestamp")
    )

    total = qs.count()
    if total <= limit:
        return list(qs)

    # Simple stride-based downsample: pick evenly-spaced indices
    step = total / limit
    indices = {int(i * step) for i in range(limit)}
    return [row for i, row in enumerate(qs) if i in indices]


# ── Events ────────────────────────────────────────────────────────────────────

@api.get("/events", response=List[EventOut])
def events(
    request: HttpRequest,
    since: Optional[datetime] = Query(None, description="Return events after this timestamp"),
    type: Optional[str] = Query(None, description="Filter by event_type"),
    limit: int = Query(100, ge=1, le=1000),
):
    qs = Event.objects.order_by("-timestamp")
    if since:
        qs = qs.filter(timestamp__gte=since)
    if type:
        qs = qs.filter(event_type=type)
    return list(qs[:limit])


# ── GPS state ─────────────────────────────────────────────────────────────────

@api.get("/gps/state", response=GpsStateOut)
def gps_state(request: HttpRequest):
    cfg = WatchdogConfig.get_solo()
    reading = TelemetryReading.objects.order_by("-timestamp").first()
    return GpsStateOut(
        valid=reading.gps_valid if reading else False,
        sats=reading.gps_sats if reading else 0,
        inhibited=reading.gps_inhibited if reading else False,
        watchdog_mode=cfg.mode,
        manual_hold_until=cfg.manual_override_until,
        last_poll_at=cfg.last_poll_at,
    )


# ── Dish info ─────────────────────────────────────────────────────────────────

@api.get("/dish/info", response=DishInfoOut)
def dish_info(request: HttpRequest):
    reading = TelemetryReading.objects.order_by("-timestamp").first()
    if reading is None:
        raise HttpError(503, "No telemetry yet — is the watchdog running?")
    return DishInfoOut(
        software_version=reading.software_version,
        country_code=reading.country_code,
        disablement_code=reading.disablement_code,
        uptime_s=reading.uptime_s,
        timestamp=reading.timestamp,
    )


# ── Watchdog config ───────────────────────────────────────────────────────────

@api.get("/watchdog/config", response=WatchdogConfigOut)
def watchdog_config(request: HttpRequest):
    cfg = WatchdogConfig.get_solo()
    return WatchdogConfigOut(
        mode=cfg.mode,
        poll_interval_s=cfg.poll_interval_s,
        deny_debounce_s=cfg.deny_debounce_s,
        recover_debounce_s=cfg.recover_debounce_s,
        min_sats_for_good=cfg.min_sats_for_good,
        boot_warmup_s=cfg.boot_warmup_s,
        manual_override_until=cfg.manual_override_until,
        last_poll_at=cfg.last_poll_at,
    )
