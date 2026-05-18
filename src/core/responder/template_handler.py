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


def _format_value(value: Any, *, bool_field: bool = False) -> str:
    """Render a telemetry value for TTS.

    Measurement fields (bool_field=False, the default):
      - bool             → "on"/"off"  (safety net; raw Python bools are always flags)
      - float            → 2 decimal places, e.g. "4.20"
      - int              → bare, e.g. "1850"
      - other            → str()

    Bool fields (bool_field=True):
      - bool, 0|1 int, 0.0|1.0 float → "on"/"off"
      - anything else                → str()

    TTTDTT emits booleans as 1.0/0.0 floats, which is why bool intents must
    be flagged explicitly: otherwise a legitimate 0.0 measurement (e.g. a
    suit-pressure reading on a paused sim) would speak as "off".
    """
    if bool_field:
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, (int, float)):
            return "on" if value == 1 else "off"
        return str(value)

    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    return str(value)


def _walk_path(payload: dict, dotted_path: str) -> Any:
    """Walk a dot-delimited path into a nested dict; KeyError on missing key."""
    node: Any = payload
    for segment in dotted_path.split("."):
        node = node[segment]
    return node


def template_handler(
    intent_label: str,
    channel: str,
    field_path: str,
    *,
    bool_field: bool = False,
) -> ResponseFn:
    template = INTENT_RESPONSE_TEMPLATES[intent_label]

    def handler(command: str, cache: Any, classification: dict) -> str:
        payload = cache.get(channel)
        if payload is None:
            return TELEMETRY_UNAVAILABLE_REPLY
        try:
            value = _walk_path(payload, field_path)
        except (KeyError, TypeError):
            return TELEMETRY_UNAVAILABLE_REPLY
        return template.format(value=_format_value(value, bool_field=bool_field))

    handler.__name__ = f"handle_{intent_label}"
    return handler
