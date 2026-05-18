"""EVA-mode hand-rolled handlers.

Most EVA labels are template_handler-driven (see registry_eva.py).
This module covers the labels that don't fit a `value_at_path` template:

  * verbal_ack(text) — UI/state-change intents (menus, procedures,
        tasks/waypoints/nav, sets, undo, ping_ltv). Python returns a
        short TTS string; Unity does the real work off the wire `intent`.
  * handle_rover_position — 3-axis composite read from pr_telemetry.rover_pos_{x,y,z}.
  * handle_last_known_position — x/y composite read from ltv.location.last_known_{x,y}.
  * handle_signal_pings_left — read from ltv.signal.ping_requested.
  * handle_error_category(keyword) — filter ltv_errors.error_procedures by description match.
"""

from collections.abc import Callable
from typing import Any

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY

ResponseFn = Callable[[str, Any, dict], str]


def verbal_ack(text: str) -> ResponseFn:
    def handler(command: str, cache: Any, classification: dict) -> str:
        return text
    return handler


def handle_rover_position(command: str, cache: Any, classification: dict) -> str:
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    try:
        pr = payload["pr_telemetry"]
        x = pr["rover_pos_x"]
        y = pr["rover_pos_y"]
        z = pr["rover_pos_z"]
    except (KeyError, TypeError):
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Rover position is X {x:.1f}, Y {y:.1f}, Z {z:.1f}."


def handle_last_known_position(command: str, cache: Any, classification: dict) -> str:
    payload = cache.get("ltv")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    try:
        loc = payload["location"]
        x = loc["last_known_x"]
        y = loc["last_known_y"]
    except (KeyError, TypeError):
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Last known position is X {x:.1f}, Y {y:.1f}."


def handle_signal_pings_left(command: str, cache: Any, classification: dict) -> str:
    payload = cache.get("ltv")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    try:
        signal = payload["signal"]
        pings = signal["ping_requested"]
    except (KeyError, TypeError):
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"{pings} pings remaining."


def handle_error_category(keyword: str, label: str) -> ResponseFn:
    """Filter ltv_errors.error_procedures by keyword match in description.

    `label` is the human-readable category name used in the response.
    """
    needle = keyword.lower()

    def handler(command: str, cache: Any, classification: dict) -> str:
        payload = cache.get("ltv_errors")
        if payload is None:
            return TELEMETRY_UNAVAILABLE_REPLY
        active = [
            err for err in payload.get("error_procedures", [])
            if err.get("needs_resolved")
            and needle in err.get("description", "").lower()
        ]
        if not active:
            return f"No active {label} errors."
        descriptions = ", ".join(err["description"] for err in active)
        return f"Active {label} errors: {descriptions}."

    handler.__name__ = f"handle_errors_{keyword}"
    return handler
