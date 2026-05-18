"""Colored event-style logging for EVA mode.

See docs/superpowers/specs/2026-05-18-eva-event-logging-design.md.
One formatter renders both per-turn event records (tagged via
extra={"event": ...}) and standard non-event records. ANSI colors
auto-disable when stderr is not a TTY.
"""

from __future__ import annotations

import logging
import os
import sys

RESET = "\033[0m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
DIM_GREY = "\033[90m"

EVENT_TAGS = {
    "mic": "[MIC]    ",
    "vad": "[VAD]    ",
    "stt": "[STT]    ",
    "intent": "[INTENT] ",
    "reply": "[REPLY]  ",
}
EVENT_COLORS = {
    "mic": CYAN,
    "vad": DIM_GREY,
    "stt": GREEN,
    "intent": YELLOW,
    "reply": MAGENTA,
}

LEVEL_COLORS = {
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: RED,
}


class EvaColorFormatter(logging.Formatter):
    """Render EVA log records.

    Event records (extra={"event": <name>}) render as `[TAG] <message>` with
    the event's color and no level/timestamp prefix. Non-event records render
    with `LEVEL name: message`, optionally colored by level.
    """

    def __init__(self, *, use_color: bool | None = None) -> None:
        super().__init__(fmt="%(levelname)s %(name)s: %(message)s")
        if use_color is None:
            use_color = sys.stderr.isatty()
        self.use_color = use_color

    def _color(self, code: str) -> str:
        return code if self.use_color else ""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if event in EVENT_TAGS:
            color = EVENT_COLORS[event]
            if event == "intent" and getattr(record, "intent_unhandled", False):
                color = RED
            tag = EVENT_TAGS[event]
            message = record.getMessage()
            return f"{self._color(color)}{tag}{message}{self._color(RESET)}"

        base = super().format(record)
        level_color = LEVEL_COLORS.get(record.levelno)
        if level_color:
            return f"{self._color(level_color)}{base}{self._color(RESET)}"
        return base


def _resolve_level(value: str | None) -> int:
    if not value:
        return logging.INFO
    name = value.strip().upper()
    level = logging.getLevelName(name)
    if isinstance(level, int):
        return level
    logging.getLogger(__name__).warning(
        "EVA_LOG_LEVEL=%r is not a known log level; falling back to INFO", value
    )
    return logging.INFO


def configure_eva_logging() -> None:
    """Install the EVA color formatter on the root logger.

    Idempotent in spirit but not by design: callers must invoke once at
    startup before other modules log. Reads EVA_LOG_LEVEL (default INFO)
    and pushes faster_whisper's chatty INFO output down to WARNING.
    """
    level = _resolve_level(os.getenv("EVA_LOG_LEVEL"))

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(EvaColorFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    if level > logging.DEBUG:
        logging.getLogger("faster_whisper").setLevel(logging.WARNING)
