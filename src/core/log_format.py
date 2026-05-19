"""Colored event-style logging shared by both CORVUS modes.

One formatter renders per-turn event records (tagged via
extra={"event": ...}) and standard non-event records. ANSI colors
auto-disable when stderr is not a TTY.

Callers pass their own event_tags / event_colors dicts so EVA and PR
modes can have distinct taxonomies ([MIC] vs [WAKE], etc.) on top of a
common formatter.
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

LEVEL_COLORS = {
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: RED,
}


class ColorFormatter(logging.Formatter):
    """Render log records with per-event tag/color overrides.

    Event records (extra={"event": <name>}) render as `[TAG] <message>` with
    the event's color and no level/timestamp prefix. Non-event records
    render with `LEVEL name: message`, optionally colored by level.
    """

    def __init__(
        self,
        *,
        event_tags: dict[str, str],
        event_colors: dict[str, str],
        use_color: bool | None = None,
    ) -> None:
        super().__init__(fmt="%(levelname)s %(name)s: %(message)s")
        if use_color is None:
            use_color = sys.stderr.isatty()
        self.use_color = use_color
        self._event_tags = event_tags
        self._event_colors = event_colors

    def _color(self, code: str) -> str:
        return code if self.use_color else ""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if event in self._event_tags:
            color = self._event_colors[event]
            if event == "intent" and getattr(record, "intent_unhandled", False):
                color = RED
            tag = self._event_tags[event]
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
        "%r is not a known log level; falling back to INFO", value
    )
    return logging.INFO


def configure_logging(
    *,
    event_tags: dict[str, str],
    event_colors: dict[str, str],
    level_env_var: str,
) -> None:
    """Install the shared color formatter on the root logger.

    Idempotent: existing root handlers are removed before installation, so
    callers may invoke this more than once (test fixtures, re-entrant
    startup paths) without stacking duplicate handlers.

    Reads ``<level_env_var>`` (default ``INFO``). Standard Python level
    *names* are accepted; numeric strings are rejected with a warning and
    treated as INFO. When the resolved level is above DEBUG, the chatty
    ``faster_whisper`` logger is pushed to WARNING so per-transcription
    "Processing audio with duration" lines stay out of default output.
    """
    level = _resolve_level(os.getenv(level_env_var))

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(ColorFormatter(event_tags=event_tags, event_colors=event_colors))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.setLevel(level)
    root.addHandler(handler)

    if level > logging.DEBUG:
        logging.getLogger("faster_whisper").setLevel(logging.WARNING)
