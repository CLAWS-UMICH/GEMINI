import logging

from src.core.log_format import ColorFormatter, configure_logging

EVA_EVENT_TAGS = {
    "mic":    "[MIC]    ",
    "vad":    "[VAD]    ",
    "stt":    "[STT]    ",
    "intent": "[INTENT] ",
    "reply":  "[REPLY]  ",
}
EVA_EVENT_COLORS = {
    "mic":    "\033[96m",
    "vad":    "\033[90m",
    "stt":    "\033[92m",
    "intent": "\033[93m",
    "reply":  "\033[95m",
}

PR_EVENT_TAGS = {
    "wake":   "[WAKE]   ",
    "vad":    "[VAD]    ",
    "stt":    "[STT]    ",
    "intent": "[INTENT] ",
    "reply":  "[REPLY]  ",
    "tts":    "[TTS]    ",
}
PR_EVENT_COLORS = {
    "wake":   "\033[96m",
    "vad":    "\033[90m",
    "stt":    "\033[92m",
    "intent": "\033[93m",
    "reply":  "\033[95m",
    "tts":    "\033[90m",
}


def _make_record(level: int = logging.INFO, msg: str = "hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="src.modes.test",
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


def test_eva_mic_event_renders_with_tag_and_color():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=True)
    record = _make_record(msg="Unity opened mic (16000 Hz mono)", event="mic")
    out = fmt.format(record)
    assert out.startswith("\033[96m[MIC]    ")
    assert out.endswith("\033[0m")
    assert "Unity opened mic (16000 Hz mono)" in out


def test_pr_wake_event_renders_with_tag_and_color():
    fmt = ColorFormatter(event_tags=PR_EVENT_TAGS, event_colors=PR_EVENT_COLORS, use_color=True)
    record = _make_record(msg="detected (score 0.83)", event="wake")
    out = fmt.format(record)
    assert out.startswith("\033[96m[WAKE]   ")
    assert out.endswith("\033[0m")
    assert "detected (score 0.83)" in out


def test_pr_tts_event_renders_with_tag_and_color():
    fmt = ColorFormatter(event_tags=PR_EVENT_TAGS, event_colors=PR_EVENT_COLORS, use_color=True)
    record = _make_record(msg="speaking 3.2s", event="tts")
    out = fmt.format(record)
    assert out.startswith("\033[90m[TTS]    ")


def test_event_renders_plain_without_tty():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=False)
    record = _make_record(msg="speech ended (2.4s captured)", event="vad")
    out = fmt.format(record)
    assert out == "[VAD]    speech ended (2.4s captured)"


def test_intent_red_when_unhandled():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=True)
    record = _make_record(msg="unhandled (conf 0.452)", event="intent", intent_unhandled=True)
    out = fmt.format(record)
    assert out.startswith("\033[91m[INTENT] ")


def test_non_event_record_uses_standard_format():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=False)
    record = _make_record(level=logging.WARNING, msg="Client disconnected")
    out = fmt.format(record)
    assert "WARNING" in out
    assert "src.modes.test" in out
    assert "Client disconnected" in out


def test_non_event_warning_colored_yellow_on_tty():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=True)
    record = _make_record(level=logging.WARNING, msg="something bad")
    out = fmt.format(record)
    assert "\033[93m" in out
    assert out.endswith("\033[0m")


def test_unknown_event_falls_back_to_non_event_format():
    fmt = ColorFormatter(event_tags=EVA_EVENT_TAGS, event_colors=EVA_EVENT_COLORS, use_color=False)
    record = _make_record(msg="weird", event="not_a_known_event")
    out = fmt.format(record)
    assert "weird" in out
    assert "[" not in out.split(":", 1)[0]  # no event tag at the start


def test_configure_logging_installs_handler_and_sets_level(monkeypatch):
    monkeypatch.delenv("PR_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        assert any(isinstance(h.formatter, ColorFormatter) for h in root.handlers)
        assert root.level == logging.INFO
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)


def test_configure_logging_honors_env_var(monkeypatch):
    monkeypatch.setenv("PR_LOG_LEVEL", "DEBUG")
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        assert root.level == logging.DEBUG
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)


def test_configure_logging_silences_faster_whisper_at_info(monkeypatch):
    monkeypatch.delenv("PR_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_fw = logging.getLogger("faster_whisper").level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        assert logging.getLogger("faster_whisper").level >= logging.WARNING
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)
        logging.getLogger("faster_whisper").setLevel(original_fw)


def test_configure_logging_is_idempotent(monkeypatch):
    monkeypatch.delenv("PR_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_fw = logging.getLogger("faster_whisper").level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        configure_logging(
            event_tags=PR_EVENT_TAGS,
            event_colors=PR_EVENT_COLORS,
            level_env_var="PR_LOG_LEVEL",
        )
        formatters = [h for h in root.handlers if isinstance(h.formatter, ColorFormatter)]
        assert len(formatters) == 1
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in original_handlers:
            root.addHandler(h)
        root.setLevel(original_level)
        logging.getLogger("faster_whisper").setLevel(original_fw)
