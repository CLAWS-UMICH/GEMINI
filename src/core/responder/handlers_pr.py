"""PR-mode response handlers.

Phase 2: most PR labels are template-driven via
`src/core/responder/template_handler.py`; the entries here are the
ones that need hand-rolled logic:

  - handle_lidar:   summarizes a 17-element vector for TTS
  - handle_set_*:   verbal-acknowledge for the 6 set_* PR intents
                    (no TSS write path yet — Phase 3 decision)

  - handle_signal_strength, handle_warnings:
        Orphan handlers — `get_signal_strength` and `get_warnings`
        are NOT in the Phase 2 multilabel label set, so they are
        unreachable from the registry. We keep them as ready-to-wire
        handlers in case a future intent catalog reintroduces them.
"""

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY


# ---------- LTV ----------

def handle_signal_strength(command, cache, classification):
    payload = cache.get("ltv")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"L T V signal strength is {round(payload['signal']['strength'], 1)}."


# ---------- LTV errors ----------

def handle_warnings(command, cache, classification):
    payload = cache.get("ltv_errors")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    active = [
        err for err in payload.get("error_procedures", [])
        if err.get("needs_resolved")
    ]
    if not active:
        return "No active warnings."
    descriptions = ", ".join(err["description"] for err in active)
    label = "Active warning" if len(active) == 1 else "Active warnings"
    return f"{label}: {descriptions}."


# ===================================================================
# Phase 2 special-case handlers (don't fit the template_handler pattern)
# ===================================================================


def handle_lidar(command, cache, classification):
    """get_lidar returns a list of 17 numbers (intentPR.json). Reading all 17
    aloud is hostile to TTS, so we summarize min/max/sample."""
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    try:
        readings = payload["pr_telemetry"]["lidar"]
    except (KeyError, TypeError):
        return TELEMETRY_UNAVAILABLE_REPLY
    if not readings:
        return "Lidar reading is empty."
    valid = [r for r in readings if r >= 0]
    if not valid:
        return "Lidar reports all sensors out of range."
    lo = min(valid)
    hi = max(valid)
    return (
        f"Lidar minimum is {lo:.1f} meters, maximum is {hi:.1f} meters "
        f"across {len(valid)} of {len(readings)} sensors."
    )


def _verbal_ack(label: str) -> str:
    """Format a set_* intent into the teammate's verbal-acknowledge template
    with status='nominal'."""
    from src.core.responder.templates import INTENT_RESPONSE_TEMPLATES
    return INTENT_RESPONSE_TEMPLATES[label].format(value="nominal")


def handle_set_cabin_cooling_on(command, cache, classification):
    return _verbal_ack("set_cabin_cooling_on")


def handle_set_cabin_cooling_off(command, cache, classification):
    return _verbal_ack("set_cabin_cooling_off")


def handle_set_cabin_heating_on(command, cache, classification):
    return _verbal_ack("set_cabin_heating_on")


def handle_set_cabin_heating_off(command, cache, classification):
    return _verbal_ack("set_cabin_heating_off")


def handle_set_lights_on(command, cache, classification):
    return _verbal_ack("set_lights_on")


def handle_set_lights_off(command, cache, classification):
    return _verbal_ack("set_lights_off")
