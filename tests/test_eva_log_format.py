import logging
import sys

import pytest

from src.modes.eva.log_format import (
    EVENT_COLORS,
    EvaColorFormatter,
    configure_eva_logging,
)


def _make_record(level: int = logging.INFO, msg: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="src.modes.eva.session",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_event_record_renders_with_tag_and_color_on_tty():
    fmt = EvaColorFormatter(use_color=True)
    record = _make_record(msg="Unity opened mic (16000 Hz mono)", event="mic")
    out = fmt.format(record)
    assert out.startswith("\033[96m[MIC]    ")
    assert out.endswith("\033[0m")
    assert "Unity opened mic (16000 Hz mono)" in out


def test_event_record_renders_plain_without_tty():
    fmt = EvaColorFormatter(use_color=False)
    record = _make_record(msg="speech ended (2.4s captured)", event="vad")
    out = fmt.format(record)
    assert out == "[VAD]    speech ended (2.4s captured)"


def test_intent_yellow_when_handled():
    fmt = EvaColorFormatter(use_color=True)
    record = _make_record(msg="vitals_heart_rate (conf 0.964)", event="intent", intent_unhandled=False)
    out = fmt.format(record)
    assert out.startswith("\033[93m[INTENT] ")


def test_intent_red_when_unhandled():
    fmt = EvaColorFormatter(use_color=True)
    record = _make_record(msg="unhandled (conf 0.452)", event="intent", intent_unhandled=True)
    out = fmt.format(record)
    assert out.startswith("\033[91m[INTENT] ")


def test_non_event_record_uses_standard_format():
    fmt = EvaColorFormatter(use_color=False)
    record = _make_record(level=logging.WARNING, msg="Client disconnected")
    out = fmt.format(record)
    assert "WARNING" in out
    assert "src.modes.eva.session" in out
    assert "Client disconnected" in out


def test_non_event_warning_colored_yellow_on_tty():
    fmt = EvaColorFormatter(use_color=True)
    record = _make_record(level=logging.WARNING, msg="something bad")
    out = fmt.format(record)
    assert "\033[93m" in out
    assert out.endswith("\033[0m")


def test_event_colors_table_covers_five_events():
    assert set(EVENT_COLORS.keys()) == {"mic", "vad", "stt", "intent", "reply"}


def test_configure_eva_logging_installs_handler_and_sets_level(monkeypatch):
    monkeypatch.delenv("EVA_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_eva_logging()
        assert any(isinstance(h.formatter, EvaColorFormatter) for h in root.handlers)
        assert root.level == logging.INFO
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)


def test_configure_eva_logging_honors_env_var(monkeypatch):
    monkeypatch.setenv("EVA_LOG_LEVEL", "DEBUG")
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_eva_logging()
        assert root.level == logging.DEBUG
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)


def test_configure_eva_logging_silences_faster_whisper_at_debug_when_root_is_info(monkeypatch):
    monkeypatch.delenv("EVA_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_fw = logging.getLogger("faster_whisper").level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_eva_logging()
        assert logging.getLogger("faster_whisper").level >= logging.WARNING
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)
        logging.getLogger("faster_whisper").setLevel(original_fw)
