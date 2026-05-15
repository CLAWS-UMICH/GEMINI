"""EVA-mode response handlers.

Each handler reads the latest EVA payload from the TelemetryCache and returns
a short TTS-ready string. On stale/missing cache, returns
TELEMETRY_UNAVAILABLE_REPLY.

Field path: payload["telemetry"]["eva1"][<field>]   (eva1 = primary astronaut)
"""

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY


def _eva1(payload):
    return payload["telemetry"]["eva1"]


def handle_heart_rate(command, cache, classification):
    payload = cache.get("eva")
    if payload is None:
        return TELEMETRY_UNAVAILABLE_REPLY
    return f"Heart rate is {round(_eva1(payload)['heart_rate'])} beats per minute."
