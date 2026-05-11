"""Per-intent response functions.

Each handler reads the latest payload for its channel from the TelemetryCache
and returns a short TTS-ready string. On stale/missing cache, it returns
TELEMETRY_UNAVAILABLE_REPLY. We trust the upstream payload contract; if a
field is missing the handler will raise KeyError and the WS layer's broad
except will surface a generic error response (spec §6, rule 2).

Field names below are best-effort guesses based on the TTTDTT event contract.
Verify against a live TTTDTT instance during the manual end-to-end check
(spec §7.4) and tighten naming in a follow-up commit if needed.
"""

from typing import Any

from src.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY


def handle_heart_rate(command: str, cache, classification) -> str:
    payload = cache.get("eva")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Heart rate is {payload['heart_bpm']} beats per minute."


def handle_batt_time_left(command: str, cache, classification) -> str:
    payload = cache.get("eva")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Suit battery has about {payload['batt_time_left']} minutes remaining."


def handle_battery_level(command: str, cache, classification) -> str:
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Rover battery is at {payload['battery_pct']} percent."


def handle_speed(command: str, cache, classification) -> str:
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Current rover speed is {payload['speed_mps']} meters per second."


def handle_signal_strength(command: str, cache, classification) -> str:
    payload = cache.get("ltv")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"L T V signal strength is {payload['signal_strength']}."


def handle_errors_nav_system(command: str, cache, classification) -> str:
    payload = cache.get("ltv_errors")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    in_error = bool(payload["nav_system"])
    return (
        "L T V navigation system is reporting an error."
        if in_error
        else "L T V navigation system is nominal."
    )
