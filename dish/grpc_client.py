"""Single chokepoint for all dish gRPC access.

Uses yagrc reflection so no vendored protobufs are needed — the service schema
is discovered from the dish on first connect and cached for the lifetime of the
process. All public functions return None/False on any error; callers must never
hard-depend on a specific field being present (SpaceX changes this API without
notice).
"""

import logging
import threading
from typing import Any, TypedDict

import grpc
from django.conf import settings
from yagrc import reflector as yagrc_reflector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10  # seconds


class StatusDict(TypedDict, total=False):
    gps_valid: bool
    gps_sats: int
    gps_inhibited: bool
    pnt_filter_state: str
    is_snr_above_noise_floor: bool
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
    raw: dict[str, Any]


class ConfigDict(TypedDict, total=False):
    snow_melt_mode: int
    location_request_mode: int
    level_dish_mode: int
    power_save_start_minutes: int
    power_save_duration_minutes: int


# --- module-level channel state (one channel per process) ---

_lock = threading.Lock()
_channel: grpc.Channel | None = None
_stub: Any = None
_request_class: Any = None


def _target() -> str:
    return getattr(settings, "DISH_GRPC_TARGET", "192.168.100.1:9200")


def _connect() -> tuple[Any, Any]:
    """Return (stub, request_class), (re)connecting and resolving reflection as needed."""
    global _channel, _stub, _request_class

    with _lock:
        if _stub is None:
            if _channel is not None:
                try:
                    _channel.close()
                except Exception:
                    pass
            _channel = grpc.insecure_channel(_target())
            ref = yagrc_reflector.GrpcReflectionClient()
            ref.load_protocols(_channel, symbols=["SpaceX.API.Device.Device"])
            _stub = ref.service_stub_class("SpaceX.API.Device.Device")(_channel)
            _request_class = ref.message_class("SpaceX.API.Device.Request")

    return _stub, _request_class


def _reset() -> None:
    global _channel, _stub, _request_class
    with _lock:
        if _channel is not None:
            try:
                _channel.close()
            except Exception:
                pass
        _channel = None
        _stub = None
        _request_class = None


def _call(request_kwargs: dict) -> Any | None:
    """Execute a single Handle() call; resets cached connection on failure."""
    for attempt in range(2):
        try:
            stub, req_cls = _connect()
            return stub.Handle(req_cls(**request_kwargs), timeout=REQUEST_TIMEOUT)
        except grpc.RpcError as e:
            code = e.code() if hasattr(e, "code") else None
            if code == grpc.StatusCode.UNIMPLEMENTED:
                logger.debug("Dish returned UNIMPLEMENTED for %s — feature absent on this firmware", request_kwargs)
                return None
            if attempt == 0:
                logger.warning("gRPC error (will retry after reconnect): %s", e)
                _reset()
            else:
                logger.error("gRPC error after reconnect: %s", e)
                return None
        except (AttributeError, ValueError, yagrc_reflector.ServiceError) as e:
            logger.error("Reflection/protocol error: %s", e)
            _reset()
            return None
    return None


# --- public API ---

def get_status() -> StatusDict | None:
    resp = _call({"get_status": {}})
    if resp is None:
        return None

    try:
        s = resp.dish_get_status
    except AttributeError:
        logger.error("get_status response missing dish_get_status")
        return None

    def _g(obj, *attrs, default=None):
        """Safely traverse a chain of attributes."""
        for attr in attrs:
            try:
                obj = getattr(obj, attr)
            except AttributeError:
                return default
        return obj if obj is not None else default

    gps = _g(s, "gps_stats")
    obs = _g(s, "obstruction_stats")
    align = _g(s, "alignment_stats")
    device_state = _g(s, "device_state")
    device_info = _g(s, "device_info")
    outage = _g(s, "outage")

    latency = _g(s, "pop_ping_latency_ms")
    if latency == -1:
        latency = None

    outage_cause = None
    if outage is not None:
        raw_cause = _g(outage, "cause")
        outage_cause = str(raw_cause) if raw_cause else None

    # MessageToDict decodes protobuf enum integers to their string names.
    # Use it as the source of truth for all enum-typed string fields.
    try:
        from google.protobuf import json_format
        raw = json_format.MessageToDict(s, preserving_proto_field_name=True)
    except Exception:
        raw = {}

    raw_gps = raw.get("gps_stats", {})
    raw_align = raw.get("alignment_stats", {})

    return StatusDict(
        gps_valid=bool(_g(gps, "gps_valid", default=False)),
        gps_sats=int(_g(gps, "gps_sats", default=0)),
        gps_inhibited=bool(_g(gps, "inhibit_gps", default=False)),
        pnt_filter_state=raw_gps.get("pnt_filter_convergence_state", ""),
        is_snr_above_noise_floor=bool(_g(s, "is_snr_above_noise_floor", default=False)),
        pop_ping_latency_ms=latency,
        pop_ping_drop_rate=float(_g(s, "pop_ping_drop_rate", default=0)),
        downlink_bps=_g(s, "downlink_throughput_bps"),
        uplink_bps=_g(s, "uplink_throughput_bps"),
        fraction_obstructed=_g(obs, "fraction_obstructed"),
        attitude_uncertainty_deg=_g(align, "attitude_uncertainty_deg"),
        attitude_state=raw_align.get("attitude_estimation_state", ""),
        uptime_s=int(_g(device_state, "uptime_s", default=0)),
        software_version=str(_g(device_info, "software_version", default="")),
        country_code=str(_g(device_info, "country_code", default="")),
        disablement_code=raw.get("disablement_code", ""),
        outage_cause=outage_cause,
        mobility_class=raw.get("mobility_class", ""),
        raw=raw,
    )


def get_config() -> ConfigDict | None:
    resp = _call({"dish_get_config": {}})
    if resp is None:
        return None

    try:
        c = resp.dish_get_config
    except AttributeError:
        return None

    def _g(obj, attr, default=None):
        return getattr(obj, attr, default)

    return ConfigDict(
        snow_melt_mode=_g(c, "snow_melt_mode"),
        location_request_mode=_g(c, "location_request_mode"),
        level_dish_mode=_g(c, "level_dish_mode"),
        power_save_start_minutes=_g(c, "power_save_start_minutes"),
        power_save_duration_minutes=_g(c, "power_save_duration_minutes"),
    )


def inhibit_gps(enabled: bool) -> bool:
    """Set GPS inhibit. enabled=True means inhibit GPS (disable it)."""
    resp = _call({"dish_inhibit_gps": {"inhibit_gps": enabled}})
    if resp is None:
        return False
    try:
        return bool(resp.dish_inhibit_gps.inhibit_gps)
    except AttributeError:
        return False


def reboot() -> bool:
    resp = _call({"reboot": {}})
    return resp is not None


def stow(stow: bool) -> bool:
    resp = _call({"dish_stow": {} if stow else {"unstow": True}})
    return resp is not None
