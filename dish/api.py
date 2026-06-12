from datetime import datetime, timedelta, timezone
from typing import List, Optional

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.utils import timezone as dj_tz
from ninja import NinjaAPI, Query
from ninja.errors import HttpError
from ninja.security import django_auth

from dish import grpc_client
from dish.models import Event, TelemetryReading, WatchdogConfig
from dish.schemas import (
    DishInfoOut,
    EventOut,
    GpsStateOut,
    InhibitGpsIn,
    LoginIn,
    MeOut,
    OkOut,
    RebootIn,
    StowIn,
    TelemetryReadingOut,
    WatchdogConfigIn,
    WatchdogConfigOut,
)

api = NinjaAPI(title="Starlink Console API", version="1.0", auth=django_auth)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api.post("/auth/login", auth=None, response=MeOut)
def auth_login(request: HttpRequest, body: LoginIn):
    user = authenticate(request, username=body.username, password=body.password)
    if user is None:
        raise HttpError(401, "Invalid credentials")
    login(request, user)
    return MeOut(username=user.username)


@api.post("/auth/logout", response=OkOut)
def auth_logout(request: HttpRequest):
    logout(request)
    return OkOut(ok=True)


@api.get("/auth/me", response=MeOut)
def auth_me(request: HttpRequest):
    return MeOut(username=request.user.username)


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


# ── Watchdog config (read) ────────────────────────────────────────────────────

@api.get("/watchdog/config", response=WatchdogConfigOut)
def watchdog_config_get(request: HttpRequest):
    cfg = WatchdogConfig.get_solo()
    return _cfg_out(cfg)


# ── Controls ──────────────────────────────────────────────────────────────────

@api.post("/control/inhibit-gps", response=GpsStateOut)
def control_inhibit_gps(request: HttpRequest, body: InhibitGpsIn):
    ok = grpc_client.inhibit_gps(body.enabled)
    if not ok:
        raise HttpError(502, "gRPC call to dish failed")

    grace = dj_tz.now() + timedelta(seconds=_grace_s())
    WatchdogConfig.objects.filter(pk=1).update(manual_override_until=grace)

    Event.objects.create(
        event_type=Event.EventType.CONTROL_ACTION,
        source=Event.Source.USER,
        actor=request.user.username,
        detail={"action": "inhibit_gps", "enabled": body.enabled, "hold_until": grace.isoformat()},
    )

    cfg = WatchdogConfig.get_solo()
    reading = TelemetryReading.objects.order_by("-timestamp").first()
    return GpsStateOut(
        valid=reading.gps_valid if reading else False,
        sats=reading.gps_sats if reading else 0,
        inhibited=body.enabled,
        watchdog_mode=cfg.mode,
        manual_hold_until=cfg.manual_override_until,
        last_poll_at=cfg.last_poll_at,
    )


@api.post("/control/reboot", response=OkOut)
def control_reboot(request: HttpRequest, body: RebootIn):
    if not body.confirm:
        raise HttpError(400, "confirm must be true")
    ok = grpc_client.reboot()
    Event.objects.create(
        event_type=Event.EventType.CONTROL_ACTION,
        source=Event.Source.USER,
        actor=request.user.username,
        detail={"action": "reboot", "success": ok},
    )
    if not ok:
        raise HttpError(502, "gRPC call to dish failed")
    return OkOut(ok=True, detail="Reboot command sent")


@api.post("/control/stow", response=OkOut)
def control_stow(request: HttpRequest, body: StowIn):
    ok = grpc_client.stow(body.stow)
    Event.objects.create(
        event_type=Event.EventType.CONTROL_ACTION,
        source=Event.Source.USER,
        actor=request.user.username,
        detail={"action": "stow", "stow": body.stow, "success": ok},
    )
    if not ok:
        raise HttpError(502, "gRPC call to dish failed")
    return OkOut(ok=True, detail="Stow command sent" if body.stow else "Unstow command sent")


@api.post("/watchdog/config", response=WatchdogConfigOut)
def watchdog_config_update(request: HttpRequest, body: WatchdogConfigIn):
    cfg = WatchdogConfig.get_solo()
    prev_mode = cfg.mode

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        WatchdogConfig.objects.filter(pk=cfg.pk).update(**updates)
        cfg.refresh_from_db()

    if body.mode and body.mode != prev_mode:
        Event.objects.create(
            event_type=Event.EventType.WATCHDOG_MODE_CHANGED,
            source=Event.Source.USER,
            actor=request.user.username,
            detail={"from": prev_mode, "to": body.mode},
        )

    return _cfg_out(cfg)


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg_out(cfg: WatchdogConfig) -> WatchdogConfigOut:
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


def _grace_s() -> int:
    from django.conf import settings
    return getattr(settings, "WATCHDOG_MANUAL_OVERRIDE_GRACE_S", 1800)
