"""Template-driven handler factory.

Spec §8: a factory that generates ~78 of the 88 handlers in bulk.

Each handler:
  1. Reads `channel` from the TelemetryCache.
  2. If absent or stale → TELEMETRY_UNAVAILABLE_REPLY.
  3. Walks the dot-delimited `field_path` to extract the value.
  4. Formats `INTENT_RESPONSE_TEMPLATES[intent_label]` with `{value}`.

Special cases (get_lidar, set_*) live alongside in handlers_pr.py /
handlers_eva.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
from src.core.responder.templates import INTENT_RESPONSE_TEMPLATES

ResponseFn = Callable[[str, Any, dict], str]


def _format_value(value: Any) -> str:
    """Render a telemetry value for TTS.

    - bool / 0.0|1.0 floats interpreted as flag → "on"/"off"
    - float → 1 decimal place
    - int → bare
    - everything else → str()
    """
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        # TTTDTT emits booleans as 1.0/0.0 floats — render them human-readable.
        if value in (0.0, 1.0):
            return "on" if value == 1.0 else "off"
        return f"{value:.1f}"
    if isinstance(value, int):
        return str(value)
    return str(value)


def _walk_path(payload: dict, dotted_path: str) -> Any:
    """Walk a dot-delimited path into a nested dict; KeyError on missing key."""
    node: Any = payload
    for segment in dotted_path.split("."):
        node = node[segment]
    return node


def template_handler(intent_label: str, channel: str, field_path: str) -> ResponseFn:
    template = INTENT_RESPONSE_TEMPLATES[intent_label]

    def handler(command: str, cache: Any, classification: dict) -> str:
        payload = cache.get(channel)
        if payload is None:
            return TELEMETRY_UNAVAILABLE_REPLY
        try:
            value = _walk_path(payload, field_path)
        except (KeyError, TypeError):
            return TELEMETRY_UNAVAILABLE_REPLY
        return template.format(value=_format_value(value))

    handler.__name__ = f"handle_{intent_label}"
    return handler
