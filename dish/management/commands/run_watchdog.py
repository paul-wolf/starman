"""Long-lived watchdog process: poll dish → persist → act.

Start in LOG_ONLY mode (the default) to observe behaviour before enabling ENFORCE.
Run as: python manage.py run_watchdog
"""

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from dish import grpc_client
from dish.connectivity import check_connectivity
from dish.models import Event, TelemetryReading, WatchdogConfig
from dish.watchdog import ConfigSnapshot, WatchdogState, evaluate

logger = logging.getLogger(__name__)

# Back-off applied when the dish is unreachable: poll_interval * this factor
UNREACHABLE_BACKOFF = 3


class Command(BaseCommand):
    help = "Long-lived watchdog: poll dish, persist telemetry, manage GPS inhibit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running = True

    def handle(self, *args, **options):
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

        self.stdout.write(self.style.SUCCESS("Watchdog starting (LOG_ONLY until mode changed in DB)"))

        state = WatchdogState()
        consecutive_failures = 0

        while self._running:
            cfg = WatchdogConfig.get_solo()
            now = timezone.now()

            connectivity_ok = check_connectivity(cfg.probe_hosts)
            status = grpc_client.get_status()

            decision = evaluate(now, status, _snapshot(cfg), state, connectivity_ok=connectivity_ok)
            state = decision.new_state

            # ── Persist telemetry (only when reachable) ──────────────────
            if status is not None:
                consecutive_failures = 0
                _write_telemetry(status, connectivity_ok=connectivity_ok)
            else:
                consecutive_failures += 1

            # ── Persist transition events ─────────────────────────────────
            for ev in decision.events:
                Event.objects.create(
                    timestamp=now,
                    event_type=ev.event_type,
                    source=Event.Source.WATCHDOG,
                    detail=ev.detail,
                )
                logger.info("Event: %s %s", ev.event_type, ev.detail)

            # ── Act on recommendation ─────────────────────────────────────
            if decision.recommended_inhibit is not None:
                _act(decision.recommended_inhibit, cfg, now)

            # ── Update heartbeat ──────────────────────────────────────────
            WatchdogConfig.objects.filter(pk=cfg.pk).update(last_poll_at=now)

            # ── Sleep ──────────────────────────────────────────────────────
            interval = cfg.poll_interval_s
            if consecutive_failures > 0:
                interval = interval * UNREACHABLE_BACKOFF
            _interruptible_sleep(interval, self._running_ref())

        self.stdout.write("Watchdog stopped.")

    def _stop(self, *_):
        self.stdout.write("Watchdog shutting down...")
        self._running = False

    def _running_ref(self):
        return lambda: self._running


# ── helpers ──────────────────────────────────────────────────────────────────

def _snapshot(cfg: WatchdogConfig) -> ConfigSnapshot:
    return ConfigSnapshot(
        mode=cfg.mode,
        deny_debounce_s=cfg.deny_debounce_s,
        recover_debounce_s=cfg.recover_debounce_s,
        min_sats_for_good=cfg.min_sats_for_good,
        boot_warmup_s=cfg.boot_warmup_s,
        manual_override_until=cfg.manual_override_until,
    )


def _write_telemetry(status: dict, connectivity_ok: bool | None = None) -> None:
    TelemetryReading.objects.create(
        gps_valid=status["gps_valid"],
        gps_sats=status["gps_sats"],
        gps_inhibited=status["gps_inhibited"],
        pnt_filter_state=status["pnt_filter_state"],
        pop_ping_latency_ms=status["pop_ping_latency_ms"],
        pop_ping_drop_rate=status["pop_ping_drop_rate"],
        downlink_bps=status["downlink_bps"],
        uplink_bps=status["uplink_bps"],
        fraction_obstructed=status["fraction_obstructed"],
        attitude_uncertainty_deg=status["attitude_uncertainty_deg"],
        attitude_state=status["attitude_state"],
        uptime_s=status["uptime_s"],
        software_version=status["software_version"],
        country_code=status["country_code"],
        disablement_code=status["disablement_code"],
        outage_cause=status["outage_cause"],
        mobility_class=status["mobility_class"],
        is_snr_above_noise_floor=status.get("is_snr_above_noise_floor"),
        connectivity_ok=connectivity_ok,
        raw_json=status.get("raw", {}),
    )


def _act(inhibit: bool, cfg: WatchdogConfig, now) -> None:
    verb = "INHIBIT" if inhibit else "CLEAR inhibit"
    mode = cfg.mode

    if mode == WatchdogConfig.Mode.ENFORCE:
        ok = grpc_client.inhibit_gps(inhibit)
        if ok:
            event_type = Event.EventType.INHIBIT_SET if inhibit else Event.EventType.INHIBIT_CLEARED
            Event.objects.create(
                timestamp=now,
                event_type=event_type,
                source=Event.Source.WATCHDOG,
                detail={"enforced": True},
            )
            logger.info("Watchdog %s (ENFORCE) — gRPC OK", verb)
        else:
            logger.error("Watchdog %s (ENFORCE) — gRPC FAILED", verb)
    else:
        # LOG_ONLY / MONITOR: record intent, never touch the dish
        event_type = Event.EventType.INHIBIT_SET if inhibit else Event.EventType.INHIBIT_CLEARED
        Event.objects.create(
            timestamp=now,
            event_type=event_type,
            source=Event.Source.WATCHDOG,
            detail={"simulated": True, "mode": mode},
        )
        logger.info("Watchdog would %s (mode=%s, not enforcing)", verb, mode)


def _interruptible_sleep(seconds: float, is_running) -> None:
    """Sleep in small chunks so SIGTERM/SIGINT is handled promptly."""
    deadline = time.monotonic() + seconds
    while is_running() and time.monotonic() < deadline:
        time.sleep(min(1.0, deadline - time.monotonic()))
