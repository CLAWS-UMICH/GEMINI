# EVA Event-Style Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace EVA's mixed `print()`+ANSI / `logging` output with a single colored-logging path that surfaces five clearly labelled per-turn events ([MIC], [VAD], [STT], [INTENT], [REPLY]) at INFO and demotes byte-drop spam, faster_whisper chatter, and latency warnings to DEBUG.

**Architecture:** One new module `src/modes/eva/log_format.py` exposes `EvaColorFormatter` and `configure_eva_logging()`. Event-tagged records carry `extra={"event": ...}` and render with hand-rolled ANSI colors when stderr is a TTY (auto-stripped otherwise). `EVA_LOG_LEVEL` env var (default INFO) gates the demoted lines. Spec: `docs/superpowers/specs/2026-05-18-eva-event-logging-design.md`.

**Tech Stack:** Python `logging` standard library, hand-rolled ANSI escape codes (no `colorama`/`rich` dependency), `pytest` + `caplog` for tests.

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `src/modes/eva/log_format.py` | `EvaColorFormatter` + `configure_eva_logging()` helper |
| Create | `tests/test_eva_log_format.py` | Formatter unit tests |
| Modify | `src/modes/eva/main.py` | Call `configure_eva_logging()` at startup; stop importing `log_*` helpers from `websocket_handler` |
| Modify | `src/modes/eva/session.py` | Emit five turn events via `extra={"event": ...}`; demote three INFO lines to DEBUG |
| Modify | `src/modes/eva/websocket_handler.py` | Delete `Colors` class + `log_*` `print` helpers; route lifecycle messages through `logging.getLogger(__name__)`; remove the `log_response()` call (REPLY is emitted from session) |

---

## Task 1: Build `EvaColorFormatter` and `configure_eva_logging`

**Files:**
- Create: `src/modes/eva/log_format.py`
- Test: `tests/test_eva_log_format.py`

- [ ] **Step 1.1: Write the failing test file**

Create `tests/test_eva_log_format.py`:

```python
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
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eva_log_format.py -v`
Expected: ImportError / ModuleNotFoundError — `src.modes.eva.log_format` does not exist.

- [ ] **Step 1.3: Implement `src/modes/eva/log_format.py`**

```python
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

# Tag (padded to 8 chars including brackets so message columns align) + color.
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

    # faster_whisper emits an INFO "Processing audio with duration ..." line
    # per transcription. Silence unless we're in DEBUG.
    if level > logging.DEBUG:
        logging.getLogger("faster_whisper").setLevel(logging.WARNING)
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `uv run pytest tests/test_eva_log_format.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add src/modes/eva/log_format.py tests/test_eva_log_format.py
git commit -m "feat(eva): add color event formatter and EVA_LOG_LEVEL config

Introduces EvaColorFormatter which renders per-turn event records
([MIC]/[VAD]/[STT]/[INTENT]/[REPLY]) with hand-rolled ANSI colors,
auto-disabled when stderr is not a TTY. configure_eva_logging() wires
it onto the root logger, reads EVA_LOG_LEVEL (default INFO), and
silences faster_whisper's per-transcription chatter when not DEBUG."
```

---

## Task 2: Wire `configure_eva_logging` into `main.py`

**Files:**
- Modify: `src/modes/eva/main.py:1-21` (imports), `src/modes/eva/main.py:25-30` (startup), `src/modes/eva/main.py:30-70` (replace `log_*` calls)

- [ ] **Step 2.1: Edit `src/modes/eva/main.py` — imports**

Replace the existing import block (lines 1-22) with:

```python
import asyncio
import logging

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient
from src.modes.eva.log_format import configure_eva_logging
from src.modes.eva.websocket_handler import start_websocket
from src.voice.stt import DEFAULT_MODEL_DIR as WHISPER_MODEL_DIR, WhisperSTT
from src.voice.vad import SileroVAD

log = logging.getLogger(__name__)
```

- [ ] **Step 2.2: Edit `src/modes/eva/main.py` — replace `logging.basicConfig` + `log_*` calls**

Replace the body of `start_server` (lines 25-58) with:

```python
async def start_server() -> None:
    configure_eva_logging()
    log.info("Starting CORVUS-EVA Server...")
    log.info("Confidence threshold: %s", CONFIDENCE_THRESH_HIGH)

    if not WHISPER_MODEL_DIR.exists():
        log.error(
            "Whisper checkpoint missing at %s. EVA mode requires Whisper for "
            "streaming PCM transcription. Run scripts/install_whisper.sh and retry.",
            WHISPER_MODEL_DIR,
        )
        raise SystemExit(1)

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log.info("TTTDTT client started (target: %s)", TTTDTT_URL)

    classifier = build_classifier(mode="eva")
    log.info("Classifier loaded (%s)", classifier.__class__.__name__)

    stt = WhisperSTT()
    log.info("Whisper STT loaded")

    vad = SileroVAD()
    log.info("Silero VAD loaded")

    try:
        await start_websocket(classifier, cache, sio_client, stt, vad, REGISTRY_EVA)
    finally:
        await sio_client.stop()
```

- [ ] **Step 2.3: Edit `src/modes/eva/main.py` — replace `log_*` calls in `main()`**

Replace `main()` (lines 61-70) with:

```python
def main() -> None:
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        log.info("Server stopped by user (Ctrl+C)")
    except SystemExit:
        raise
    except Exception:
        log.exception("Server crashed")
        raise
```

- [ ] **Step 2.4: Sanity-check the module imports and the existing EVA tests still pass**

Run: `uv run python -c "from src.modes.eva.main import main; print('ok')"`
Expected: `ok`

Run: `uv run pytest tests/test_eva_session.py tests/test_eva_handler_e2e.py tests/test_eva_protocol.py -v`
Expected: all PASS (no test depends on `log_*` helpers; the existing tests don't assert on log lines).

- [ ] **Step 2.5: Commit**

```bash
git add src/modes/eva/main.py
git commit -m "refactor(eva): route main.py through configure_eva_logging

Drops the local logging.basicConfig and the log_info/log_success/log_error
imports from websocket_handler. main.py now calls configure_eva_logging()
once at startup and uses module-level logger.info/error/exception, which
the new EvaColorFormatter renders consistently."
```

---

## Task 3: Emit the five turn events from `session.py` and demote noise to DEBUG

**Files:**
- Modify: `src/modes/eva/session.py:92-103` (MIC event), `:118-122` (drop bytes → DEBUG), `:164-170` (VAD event), `:172-230` (STT/INTENT/REPLY events + demote latency + demote final summary)

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_eva_session.py`:

```python
def test_mic_event_emitted_on_start(caplog):
    session = make_session()
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))

    mic_records = [r for r in caplog.records if getattr(r, "event", None) == "mic"]
    assert len(mic_records) == 1
    assert "16000" in mic_records[0].getMessage()


def test_vad_event_emitted_on_end_of_speech(caplog):
    vad = FakeVAD(sequence=[True] + [False] * 25)
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    pcm = _pcm_nonzero_bytes(VAD_FRAME_SAMPLES * 26)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        session.on_binary(pcm)

    vad_records = [r for r in caplog.records if getattr(r, "event", None) == "vad"]
    assert len(vad_records) == 1
    assert "s captured" in vad_records[0].getMessage()


def test_finalize_emits_stt_intent_reply_events(caplog):
    vad = FakeVAD()
    stt = FakeSTT(transcript="check heart rate")
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.95})
    registry = {"vitals_heart_rate": lambda *a: "HR is 72 bpm."}
    session = make_session(vad=vad, stt=stt, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    events = {getattr(r, "event", None): r for r in caplog.records}
    assert "stt" in events
    assert "check heart rate" in events["stt"].getMessage()
    assert "intent" in events
    assert "vitals_heart_rate" in events["intent"].getMessage()
    assert getattr(events["intent"], "intent_unhandled", False) is False
    assert "reply" in events
    assert "HR is 72 bpm." in events["reply"].getMessage()


def test_finalize_intent_event_flags_unhandled(caplog):
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.20})
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    intent_records = [r for r in caplog.records if getattr(r, "event", None) == "intent"]
    assert len(intent_records) == 1
    assert intent_records[0].intent_unhandled is True


def test_dropping_bytes_is_debug_not_info(caplog):
    session = make_session()
    with caplog.at_level("DEBUG", logger="src.modes.eva.session"):
        session.on_binary(_pcm_silence_bytes(1600))

    drop_records = [r for r in caplog.records if "dropping" in r.getMessage()]
    assert len(drop_records) == 1
    assert drop_records[0].levelno == logging.DEBUG


def test_latency_warning_is_debug(caplog, monkeypatch):
    # Force the latency-warning path by making the threshold ridiculously small.
    monkeypatch.setattr("src.modes.eva.session.LATENCY_WARNING_MS", 0)
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.95})
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("DEBUG", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    latency_records = [r for r in caplog.records if "high latency" in r.getMessage()]
    assert len(latency_records) == 1
    assert latency_records[0].levelno == logging.DEBUG
```

Also add the `import logging` line at the top of `tests/test_eva_session.py` if it isn't already imported (it isn't — add it next to `import json`).

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eva_session.py -v -k "mic_event or vad_event or stt_intent_reply or intent_event_flags or dropping_bytes_is_debug or latency_warning_is_debug"`
Expected: 6 FAILs — either no `event` attribute on records, or wrong log level.

- [ ] **Step 3.3: Edit `src/modes/eva/session.py` — MIC event**

Replace line 102:

```python
        log.info("eva: state IDLE -> BUFFERING")
```

With:

```python
        log.info(
            "Unity opened mic (%d Hz mono)",
            msg.sample_rate,
            extra={"event": "mic"},
        )
```

- [ ] **Step 3.4: Edit `src/modes/eva/session.py` — drop bytes → DEBUG**

Replace line 120:

```python
            log.info("eva: dropping %d bytes received in IDLE state", len(data))
```

With:

```python
            log.debug("eva: dropping %d bytes received in IDLE state", len(data))
```

- [ ] **Step 3.5: Edit `src/modes/eva/session.py` — VAD event**

Replace lines 166-168 inside `_end_of_speech`:

```python
        pcm = bytes(self._buffer)
        ready = AudioReady(pcm=pcm, processing_start=time.monotonic())
        self.state = SessionState.IDLE
        log.info("eva: state BUFFERING -> IDLE (end-of-speech, %d bytes)", len(pcm))
```

With:

```python
        pcm = bytes(self._buffer)
        ready = AudioReady(pcm=pcm, processing_start=time.monotonic())
        self.state = SessionState.IDLE
        duration_s = len(pcm) / 32000  # 16000 samples/s * 2 bytes/sample
        log.info(
            "speech ended (%.1fs captured)",
            duration_s,
            extra={"event": "vad"},
        )
```

- [ ] **Step 3.6: Edit `src/modes/eva/session.py` — STT, INTENT, REPLY events**

Inside `finalize`, **after** the STT try/except block (i.e. after the `except Exception: ... return FinalMsg(response="")` on line 178, before the next `try:` on line 180) so the STT event only fires when transcription succeeded, insert:

```python
        log.info("%r", transcript, extra={"event": "stt"})
```

After the existing `intent = raw_intent if (...)` line (line 194), insert:

```python
        log.info(
            "%s (conf %.3f)",
            intent,
            confidence,
            extra={"event": "intent", "intent_unhandled": intent == "unhandled"},
        )
```

Replace the block at lines 207-208 (latency warning):

```python
        if latency_ms > LATENCY_WARNING_MS:
            log.warning("eva: high latency %sms (threshold %sms)", latency_ms, LATENCY_WARNING_MS)
```

With:

```python
        if latency_ms > LATENCY_WARNING_MS:
            log.debug("eva: high latency %sms (threshold %sms)", latency_ms, LATENCY_WARNING_MS)
```

Replace the block at lines 216-222 (final summary):

```python
        log.info(
            "eva: final intent=%s confidence=%.3f latency_ms=%s transcript=%r",
            intent,
            confidence,
            latency_ms,
            transcript,
        )
```

With:

```python
        log.info(
            "%s",
            response_text,
            extra={"event": "reply"},
        )
        log.debug(
            "eva: final intent=%s confidence=%.3f latency_ms=%s transcript=%r",
            intent,
            confidence,
            latency_ms,
            transcript,
        )
```

- [ ] **Step 3.7: Run new tests to verify they pass**

Run: `uv run pytest tests/test_eva_session.py -v -k "mic_event or vad_event or stt_intent_reply or intent_event_flags or dropping_bytes_is_debug or latency_warning_is_debug"`
Expected: 6 PASSes.

- [ ] **Step 3.8: Run the full session test file to confirm no regressions**

Run: `uv run pytest tests/test_eva_session.py -v`
Expected: all PASS.

- [ ] **Step 3.9: Commit**

```bash
git add src/modes/eva/session.py tests/test_eva_session.py
git commit -m "feat(eva): emit five tagged turn events from session

Replaces the per-turn INFO chatter (state IDLE->BUFFERING, state
BUFFERING->IDLE (end-of-speech, ... bytes), final intent=... summary)
with five tagged events: [MIC] on start, [VAD] on end-of-speech, [STT]
on transcript, [INTENT] on classified intent (flagged unhandled when
gate folds), [REPLY] on response. Demotes dropping-bytes spam, latency
warnings, and the final-summary correlation line to DEBUG so they
remain recoverable via EVA_LOG_LEVEL=DEBUG."
```

---

## Task 4: Clean up `websocket_handler.py`

**Files:**
- Modify: `src/modes/eva/websocket_handler.py:1-87` (remove `Colors` + `log_*` helpers; route through `logging`; remove `log_response` call)

- [ ] **Step 4.1: Write a failing test for the lifecycle logging**

Append to `tests/test_eva_handler_e2e.py`:

```python
def test_websocket_handler_does_not_define_print_helpers():
    """Regression: the print()/ANSI log_* helpers and Colors class are gone.

    They were replaced by the logging-based path so EvaColorFormatter
    can render lifecycle messages consistently with turn events.
    """
    from src.modes.eva import websocket_handler

    assert not hasattr(websocket_handler, "Colors")
    assert not hasattr(websocket_handler, "log_info")
    assert not hasattr(websocket_handler, "log_success")
    assert not hasattr(websocket_handler, "log_warning")
    assert not hasattr(websocket_handler, "log_error")
    assert not hasattr(websocket_handler, "log_response")
```

- [ ] **Step 4.2: Run the test to verify it fails**

Run: `uv run pytest tests/test_eva_handler_e2e.py::test_websocket_handler_does_not_define_print_helpers -v`
Expected: FAIL — the helpers still exist.

- [ ] **Step 4.3: Rewrite `src/modes/eva/websocket_handler.py`**

Replace the entire file content with:

```python
import asyncio
import logging

import websockets

from src.config import HOST, PORT
from src.modes.eva.protocol import serialize_final
from src.modes.eva.session import AudioReady, EvaSession

logger = logging.getLogger(__name__)


def _make_client_handler(classifier, cache, sio_client, stt, vad, registry):
    async def handle_client(websocket):
        client_address = websocket.remote_address
        logger.info("Client connected: %s", client_address)
        session = EvaSession(
            vad=vad,
            stt=stt,
            classifier=classifier,
            cache=cache,
            sio_client=sio_client,
            registry=registry,
        )
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    ready = session.on_binary(message)
                    if isinstance(ready, AudioReady):
                        final = await session.finalize(ready)
                        await websocket.send(serialize_final(final))
                else:
                    session.on_text(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Client disconnected: %s", client_address)
        except Exception:
            logger.exception("Error handling client %s", client_address)
        finally:
            logger.info("Connection closed: %s", client_address)

    return handle_client


async def start_websocket(classifier, cache, sio_client, stt, vad, registry) -> None:
    logger.info("Starting CORVUS-EVA WebSocket Server...")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)

    handler = _make_client_handler(classifier, cache, sio_client, stt, vad, registry)
    async with websockets.serve(handler, HOST, PORT):
        logger.info("Server running on ws://%s:%s", HOST, PORT)
        logger.info("Waiting for Unity connection...")
        logger.info("Press Ctrl+C to stop the server")
        await asyncio.Future()
```

Note: `log_response(final.response)` is gone — the `[REPLY]` event emitted from `session.finalize()` covers it.

- [ ] **Step 4.4: Run the regression test and the full EVA suite**

Run: `uv run pytest tests/test_eva_handler_e2e.py tests/test_eva_session.py tests/test_eva_protocol.py tests/test_eva_log_format.py -v`
Expected: all PASS.

- [ ] **Step 4.5: Manual smoke test (live)**

Run: `uv run corvus-eva` in one terminal. Connect Unity (or any WS client that follows the protocol) in another. Verify in the EVA terminal:

1. Startup lines render plainly (no `[INFO]`/`[SUCCESS]` `print()` tags), colored yellow at WARNING/red at ERROR if any occur.
2. On a successful turn, you see exactly five lines:
   - cyan `[MIC]    Unity opened mic (16000 Hz mono)`
   - dim grey `[VAD]    speech ended (X.Xs captured)`
   - green `[STT]    'transcript'`
   - yellow `[INTENT] some_intent (conf 0.NNN)` (red if unhandled)
   - magenta `[REPLY]  response string`
3. No more spam of `eva: dropping N bytes received in IDLE state` between turns.
4. Pipe the output to a file: `uv run corvus-eva 2>&1 | tee /tmp/eva.log`. Open `/tmp/eva.log` and confirm there are no raw `\033[` sequences (TTY auto-detect should strip them).
5. `EVA_LOG_LEVEL=DEBUG uv run corvus-eva` brings back the dropping-bytes, the latency warnings, and the `eva: final intent=…` correlation line.

If any of those fail, fix and re-run before committing.

- [ ] **Step 4.6: Commit**

```bash
git add src/modes/eva/websocket_handler.py tests/test_eva_handler_e2e.py
git commit -m "refactor(eva): drop print/ANSI helpers from websocket_handler

Removes the Colors class and log_info/log_success/log_warning/log_error/
log_response print() helpers. Lifecycle messages now flow through
logging.getLogger(__name__) so EvaColorFormatter renders them with
the same TTY-aware coloring as turn events. The log_response call is
gone because session.finalize already emits a [REPLY] event."
```

---

## Final verification

- [ ] **Run the full test suite one more time**

Run: `uv run pytest -v`
Expected: all PASS, no regressions outside the EVA logging area.

- [ ] **Confirm no rogue `print(` calls in EVA mode**

Run: `grep -nR "print(" src/modes/eva/`
Expected: no matches.
