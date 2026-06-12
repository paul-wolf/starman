from datetime import datetime, timedelta, timezone
from unittest import TestCase

from dish.watchdog import ConfigSnapshot, WatchdogState, evaluate

UTC = timezone.utc


def t(offset_s: float = 0) -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC) + timedelta(seconds=offset_s)


def cfg(**overrides) -> ConfigSnapshot:
    defaults = dict(
        mode="ENFORCE",
        deny_debounce_s=90,
        recover_debounce_s=120,
        min_sats_for_good=5,
        boot_warmup_s=300,
        manual_override_until=None,
    )
    defaults.update(overrides)
    return ConfigSnapshot(**defaults)


def good_status(**overrides) -> dict:
    base = dict(
        gps_valid=True,
        gps_sats=8,
        gps_inhibited=False,
        pnt_filter_state="",
        pop_ping_latency_ms=30.0,
        pop_ping_drop_rate=0.0,
        downlink_bps=1e6,
        uplink_bps=5e5,
        fraction_obstructed=0.0,
        attitude_uncertainty_deg=1.0,
        attitude_state="",
        uptime_s=1000,
        software_version="2024.01.01",
        country_code="UA",
        disablement_code="",
        outage_cause=None,
        mobility_class="",
        raw={},
    )
    base.update(overrides)
    return base


def denied_status(**overrides) -> dict:
    return good_status(gps_valid=False, gps_sats=0, **overrides)


def event_types(decision) -> set:
    return {e.event_type for e in decision.events}


class UnreachableTests(TestCase):
    def test_emits_event_once(self):
        state = WatchdogState()
        d1 = evaluate(t(0), None, cfg(), state)
        self.assertIn("DISH_UNREACHABLE", event_types(d1))

        d2 = evaluate(t(10), None, cfg(), d1.new_state)
        self.assertNotIn("DISH_UNREACHABLE", event_types(d2))

    def test_no_inhibit_recommendation(self):
        d = evaluate(t(0), None, cfg(), WatchdogState())
        self.assertIsNone(d.recommended_inhibit)

    def test_resets_debounce(self):
        state = WatchdogState(gps_denied_since=t(-100), last_gps_good=False, last_uptime_s=500)
        d = evaluate(t(0), None, cfg(), state)
        self.assertIsNone(d.new_state.gps_denied_since)
        self.assertIsNone(d.new_state.last_gps_good)


class BootWarmupTests(TestCase):
    def test_suppresses_action(self):
        state = WatchdogState(last_uptime_s=50)
        d = evaluate(t(0), denied_status(uptime_s=100), cfg(boot_warmup_s=300), state)
        self.assertIsNone(d.recommended_inhibit)

    def test_resets_denied_timer(self):
        state = WatchdogState(gps_denied_since=t(-200), last_uptime_s=50, last_gps_good=False)
        d = evaluate(t(0), denied_status(uptime_s=100), cfg(boot_warmup_s=300), state)
        self.assertIsNone(d.new_state.gps_denied_since)


class RebootDetectionTests(TestCase):
    def test_detected_on_uptime_drop(self):
        state = WatchdogState(last_uptime_s=5000)
        d = evaluate(t(0), good_status(uptime_s=30), cfg(), state)
        self.assertIn("REBOOT_DETECTED", event_types(d))

    def test_resets_debounce(self):
        state = WatchdogState(last_uptime_s=5000, gps_denied_since=t(-200), last_gps_good=False)
        d = evaluate(t(0), denied_status(uptime_s=30), cfg(), state)
        self.assertIsNone(d.new_state.gps_denied_since)

    def test_not_on_first_poll(self):
        d = evaluate(t(0), good_status(uptime_s=30), cfg(), WatchdogState())
        self.assertNotIn("REBOOT_DETECTED", event_types(d))


class GpsTransitionTests(TestCase):
    def test_denied_event_on_transition(self):
        state = WatchdogState()
        d1 = evaluate(t(0), good_status(), cfg(), state)
        self.assertNotIn("GPS_DENIED", event_types(d1))

        d2 = evaluate(t(10), denied_status(), cfg(), d1.new_state)
        self.assertIn("GPS_DENIED", event_types(d2))

        d3 = evaluate(t(20), denied_status(), cfg(), d2.new_state)
        self.assertNotIn("GPS_DENIED", event_types(d3))

    def test_recovered_event_on_transition(self):
        state = WatchdogState(last_gps_good=False, gps_denied_since=t(-200))
        d = evaluate(t(0), good_status(), cfg(), state)
        self.assertIn("GPS_RECOVERED", event_types(d))

    def test_no_event_on_first_poll(self):
        d = evaluate(t(0), denied_status(), cfg(), WatchdogState())
        self.assertNotIn("GPS_DENIED", event_types(d))
        self.assertNotIn("GPS_RECOVERED", event_types(d))


class InhibitRecommendationTests(TestCase):
    def test_recommended_after_debounce(self):
        state = WatchdogState(gps_denied_since=t(-100), last_gps_good=False, last_uptime_s=1000)
        d = evaluate(t(0), denied_status(uptime_s=1000), cfg(deny_debounce_s=90), state)
        self.assertTrue(d.recommended_inhibit)

    def test_not_before_debounce(self):
        state = WatchdogState(gps_denied_since=t(-50), last_gps_good=False, last_uptime_s=1000)
        d = evaluate(t(0), denied_status(uptime_s=1000), cfg(deny_debounce_s=90), state)
        self.assertIsNone(d.recommended_inhibit)

    def test_not_if_already_inhibited(self):
        state = WatchdogState(gps_denied_since=t(-100), last_gps_good=False, last_uptime_s=1000)
        d = evaluate(t(0), denied_status(uptime_s=1000, gps_inhibited=True), cfg(deny_debounce_s=90), state)
        self.assertIsNone(d.recommended_inhibit)

    def test_clear_recommended_after_recover_debounce(self):
        state = WatchdogState(gps_good_since=t(-130), last_gps_good=True, last_uptime_s=1000)
        d = evaluate(t(0), good_status(uptime_s=1000, gps_inhibited=True), cfg(recover_debounce_s=120), state)
        self.assertFalse(d.recommended_inhibit)

    def test_no_clear_before_recover_debounce(self):
        state = WatchdogState(gps_good_since=t(-60), last_gps_good=True, last_uptime_s=1000)
        d = evaluate(t(0), good_status(uptime_s=1000, gps_inhibited=True), cfg(recover_debounce_s=120), state)
        self.assertIsNone(d.recommended_inhibit)

    def test_no_clear_if_not_inhibited(self):
        state = WatchdogState(gps_good_since=t(-130), last_gps_good=True, last_uptime_s=1000)
        d = evaluate(t(0), good_status(uptime_s=1000, gps_inhibited=False), cfg(recover_debounce_s=120), state)
        self.assertIsNone(d.recommended_inhibit)


class ManualOverrideTests(TestCase):
    def test_blocks_clear(self):
        state = WatchdogState(gps_good_since=t(-130), last_gps_good=True, last_uptime_s=1000)
        d = evaluate(
            t(0),
            good_status(uptime_s=1000, gps_inhibited=True),
            cfg(recover_debounce_s=120, manual_override_until=t(3600)),
            state,
        )
        self.assertIsNone(d.recommended_inhibit)

    def test_does_not_block_inhibit(self):
        state = WatchdogState(gps_denied_since=t(-100), last_gps_good=False, last_uptime_s=1000)
        d = evaluate(
            t(0),
            denied_status(uptime_s=1000, gps_inhibited=False),
            cfg(deny_debounce_s=90, manual_override_until=t(3600)),
            state,
        )
        self.assertTrue(d.recommended_inhibit)

    def test_expired_override_allows_clear(self):
        state = WatchdogState(gps_good_since=t(-130), last_gps_good=True, last_uptime_s=1000)
        d = evaluate(
            t(0),
            good_status(uptime_s=1000, gps_inhibited=True),
            cfg(recover_debounce_s=120, manual_override_until=t(-1)),
            state,
        )
        self.assertFalse(d.recommended_inhibit)


class OutageTrackingTests(TestCase):
    def test_outage_start_event(self):
        state = WatchdogState(last_uptime_s=1000, last_gps_good=True)
        d = evaluate(t(0), good_status(uptime_s=1010, outage_cause="NO_SATS"), cfg(), state)
        self.assertIn("OUTAGE_START", event_types(d))

    def test_outage_end_event(self):
        state = WatchdogState(last_uptime_s=1000, last_outage_cause="NO_SATS", last_gps_good=True)
        d = evaluate(t(0), good_status(uptime_s=1010, outage_cause=None), cfg(), state)
        self.assertIn("OUTAGE_END", event_types(d))

    def test_no_duplicate_outage_start(self):
        state = WatchdogState(last_uptime_s=1000, last_outage_cause="NO_SATS", last_gps_good=True)
        d = evaluate(t(0), good_status(uptime_s=1010, outage_cause="NO_SATS"), cfg(), state)
        self.assertNotIn("OUTAGE_START", event_types(d))
