"""Pure watchdog decision logic — no Django, no IO, fully unit-testable.

The management command run_watchdog owns all IO (gRPC calls, DB writes, sleep).
This module only computes what *should* happen given the current inputs.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ConfigSnapshot:
    """Immutable copy of WatchdogConfig fields passed into evaluate()."""
    mode: str
    deny_debounce_s: int
    recover_debounce_s: int
    min_sats_for_good: int
    boot_warmup_s: int
    manual_override_until: datetime | None


@dataclass
class WatchdogState:
    gps_denied_since: datetime | None = None
    gps_good_since: datetime | None = None
    last_uptime_s: int | None = None
    last_gps_good: bool | None = None   # None = unknown (startup or post-gap)
    last_outage_cause: str | None = None
    dish_unreachable: bool = False
    net_outage_active: bool = False
    logical_inhibited: bool = False   # tracks "as if enforced" inhibit in LOG_ONLY/MONITOR


@dataclass
class EventSpec:
    event_type: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchdogDecision:
    """
    recommended_inhibit:
        True  — logic says we should set inhibit
        False — logic says we should clear inhibit
        None  — no change recommended
    events: transition events to persist (regardless of mode)
    new_state: state to carry into the next poll
    """
    recommended_inhibit: bool | None
    events: list[EventSpec]
    new_state: WatchdogState


def evaluate(
    now: datetime,
    status: dict | None,     # StatusDict from grpc_client, or None if unreachable
    config: ConfigSnapshot,
    state: WatchdogState,
    *,
    connectivity_ok: bool | None = None,
) -> WatchdogDecision:
    events: list[EventSpec] = []
    s = replace(state)  # shallow copy; we mutate s below

    # ── Network connectivity (independent of dish reachability) ────────────
    if connectivity_ok is not None:
        if not connectivity_ok and not state.net_outage_active:
            events.append(EventSpec("NET_OUTAGE_START", {}))
            s.net_outage_active = True
        elif connectivity_ok and state.net_outage_active:
            events.append(EventSpec("NET_OUTAGE_END", {}))
            s.net_outage_active = False

    # ── Dish unreachable ────────────────────────────────────────────────────
    if status is None:
        if not state.dish_unreachable:
            events.append(EventSpec("DISH_UNREACHABLE"))
        s.gps_denied_since = None
        s.gps_good_since = None
        s.last_gps_good = None
        s.dish_unreachable = True
        return WatchdogDecision(recommended_inhibit=None, events=events, new_state=s)

    s.dish_unreachable = False

    # ── Reboot detection ────────────────────────────────────────────────────
    uptime = status["uptime_s"]
    if state.last_uptime_s is not None and uptime < state.last_uptime_s:
        events.append(EventSpec("REBOOT_DETECTED", {
            "prev_uptime_s": state.last_uptime_s,
            "uptime_s": uptime,
        }))
        s.gps_denied_since = None
        s.gps_good_since = None
        s.last_gps_good = None
        s.logical_inhibited = False   # fresh boot clears any simulated inhibit

    s.last_uptime_s = uptime

    # ── Outage transitions ──────────────────────────────────────────────────
    cause = status.get("outage_cause")
    if cause and not state.last_outage_cause:
        events.append(EventSpec("OUTAGE_START", {"cause": cause}))
    elif not cause and state.last_outage_cause:
        events.append(EventSpec("OUTAGE_END", {"cause": state.last_outage_cause}))
    s.last_outage_cause = cause

    # ── Boot warmup — no GPS action, reset debounce ─────────────────────────
    if uptime < config.boot_warmup_s:
        s.gps_denied_since = None
        s.gps_good_since = None
        return WatchdogDecision(recommended_inhibit=None, events=events, new_state=s)

    # ── GPS state ────────────────────────────────────────────────────────────
    gps_good = bool(status["gps_valid"]) and int(status["gps_sats"]) >= config.min_sats_for_good

    if state.last_gps_good is not None:
        if gps_good and not state.last_gps_good:
            events.append(EventSpec("GPS_RECOVERED", {"sats": status["gps_sats"]}))
        elif not gps_good and state.last_gps_good:
            events.append(EventSpec("GPS_DENIED", {
                "sats": status["gps_sats"],
                "gps_valid": status["gps_valid"],
            }))

    s.last_gps_good = gps_good

    # Effective inhibit: actual dish state OR our logical tracking.
    # In ENFORCE mode these converge after one poll; in LOG_ONLY/MONITOR mode
    # logical_inhibited is the only record that we already "handled" this event,
    # preventing repeated INHIBIT_SET and enabling INHIBIT_CLEARED simulation.
    effective_inhibited = status["gps_inhibited"] or state.logical_inhibited

    recommended: bool | None = None

    if gps_good:
        s.gps_denied_since = None
        if s.gps_good_since is None:
            s.gps_good_since = now
        good_s = (now - s.gps_good_since).total_seconds()

        # Recommend clearing inhibit after recover debounce, unless user hold is active.
        # The hold blocks auto-CLEAR (user chose to inhibit; don't fight them).
        if (
            good_s >= config.recover_debounce_s
            and effective_inhibited
            and not _override_active(config, now)
        ):
            recommended = False
            s.logical_inhibited = False

    else:
        s.gps_good_since = None
        if s.gps_denied_since is None:
            s.gps_denied_since = now
        denied_s = (now - s.gps_denied_since).total_seconds()

        # Recommend inhibit after deny debounce.
        # Safety beats the manual hold: we still inhibit on genuine sustained denial.
        if denied_s >= config.deny_debounce_s and not effective_inhibited:
            recommended = True
            s.logical_inhibited = True

    return WatchdogDecision(recommended_inhibit=recommended, events=events, new_state=s)


def _override_active(config: ConfigSnapshot, now: datetime) -> bool:
    return bool(config.manual_override_until and now < config.manual_override_until)
