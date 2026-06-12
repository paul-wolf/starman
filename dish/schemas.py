from datetime import datetime
from typing import Optional

from ninja import Schema


class TelemetryReadingOut(Schema):
    id: int
    timestamp: datetime
    gps_valid: bool
    gps_sats: int
    gps_inhibited: bool
    pnt_filter_state: str
    pop_ping_latency_ms: float | None
    pop_ping_drop_rate: float
    downlink_bps: float | None
    uplink_bps: float | None
    fraction_obstructed: float | None
    attitude_uncertainty_deg: float | None
    attitude_state: str
    uptime_s: int
    software_version: str
    country_code: str
    disablement_code: str
    outage_cause: str | None
    mobility_class: str


class EventOut(Schema):
    id: int
    timestamp: datetime
    event_type: str
    source: str
    actor: str | None
    detail: dict


class GpsStateOut(Schema):
    valid: bool
    sats: int
    inhibited: bool
    watchdog_mode: str
    manual_hold_until: datetime | None
    last_poll_at: datetime | None


class DishInfoOut(Schema):
    software_version: str
    country_code: str
    disablement_code: str
    uptime_s: int
    timestamp: datetime


class WatchdogConfigOut(Schema):
    mode: str
    poll_interval_s: int
    deny_debounce_s: int
    recover_debounce_s: int
    min_sats_for_good: int
    boot_warmup_s: int
    manual_override_until: datetime | None
    last_poll_at: datetime | None


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginIn(Schema):
    username: str
    password: str


class MeOut(Schema):
    username: str


# ── Control inputs ────────────────────────────────────────────────────────────

class InhibitGpsIn(Schema):
    enabled: bool


class RebootIn(Schema):
    confirm: bool


class StowIn(Schema):
    stow: bool


class WatchdogConfigIn(Schema):
    mode: Optional[str] = None
    poll_interval_s: Optional[int] = None
    deny_debounce_s: Optional[int] = None
    recover_debounce_s: Optional[int] = None
    min_sats_for_good: Optional[int] = None


# ── Generic responses ─────────────────────────────────────────────────────────

class OkOut(Schema):
    ok: bool
    detail: str = ""
