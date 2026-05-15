"""PR-mode response handlers (rover + LTV channels).

Each handler reads the latest payload for its channel from the TelemetryCache
and returns a short TTS-ready string. On stale/missing cache, returns
TELEMETRY_UNAVAILABLE_REPLY.

Field paths come from the live TTTDTT event contract observed against NASA TSS:

- "rover":      payload["pr_telemetry"][<field>]
- "ltv":        payload["signal"][<field>] or payload["location"][<field>]
- "ltv_errors": payload["error_procedures"] is a list of dicts

If a field is missing the handler raises KeyError; the WS layer's broad
except surfaces a generic error response (spec §6, rule 2).
"""

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY


def _rover(payload):
    return payload["pr_telemetry"]


# ---------- Rover ----------

def handle_battery_level(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Rover primary battery is at {round(_rover(payload)['primary_battery_level'], 1)} percent."


def handle_speed(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Current rover speed is {round(_rover(payload)['speed'], 2)} meters per second."


def handle_oxygen_pressure(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Rover oxygen pressure is {round(_rover(payload)['oxygen_pressure'])} P S I."


def handle_oxygen_tank(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Rover oxygen storage is at {round(_rover(payload)['oxygen_storage'], 1)} percent."


def handle_cabin_pressure(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Cabin pressure is {round(_rover(payload)['cabin_pressure'], 2)} P S I."


def handle_cabin_temperature(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Cabin temperature is {round(_rover(payload)['cabin_temperature'], 1)} degrees Celsius."


def handle_external_temp(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"External temperature is {round(_rover(payload)['external_temp'], 1)} degrees Celsius."


def handle_heading(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Current heading is {round(_rover(payload)['heading'])} degrees."


def handle_distance_traveled(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Distance traveled is {round(_rover(payload)['distance_traveled'])} meters."


def handle_surface_incline(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Surface incline is {round(_rover(payload)['surface_incline'], 1)} degrees."


def handle_throttle(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Throttle is at {round(_rover(payload)['throttle'], 1)} percent."


def handle_sunlight(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Sunlight is at {round(_rover(payload)['sunlight'] * 100)} percent."


def handle_coolant_pressure(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Coolant pressure is {round(_rover(payload)['coolant_pressure'])} P S I."


def handle_coolant_storage(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Coolant storage is at {round(_rover(payload)['coolant_storage'], 1)} percent."


def handle_rover_elapsed_time(command, cache, classification):
    payload = cache.get("rover")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    minutes = _rover(payload)["rover_elapsed_time"] // 60
    return f"Rover has been running for {minutes} minutes."


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
