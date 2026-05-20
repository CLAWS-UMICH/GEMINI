# PR-side finalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize the CORVUS PR side: port EVA's event-tagged logging (adding `[WAKE]`/`[TTS]`), eliminate wake-word re-fires after a single utterance, and let PR mode answer EVA telemetry queries in addition to its 43 rover queries.

**Architecture:** Three independent concerns. (1) Lift EVA's formatter to `src/core/log_format.py`, parameterize on event-tag dict + env var, migrate both modes. (2) Three-state audio mux (`wake` / `capture` / `playback`) with `WakeWordDetector.reset()` + 300 ms cooldown on every `playback→wake` transition. (3) `MultilabelClassifier(mode="pr")` loads the union of `intentPR.json` + `intenteva.json` masks; the PR registry grows from 43 to 88 entries by adding a 45-row `_EVA_FIELD_PATHS` table fed through the existing `template_handler` factory.

**Tech Stack:** Python 3.13, `logging` stdlib, `sounddevice` for audio I/O, openWakeWord 0.6.x, faster-whisper, Piper 1.4.x, PyTorch 2.9, pytest.

**Source spec:** `docs/superpowers/specs/2026-05-18-pr-side-finalization-design.md`

---

## File structure

**Created:**
- `src/core/log_format.py` — shared parameterized formatter (lifted from `src/modes/eva/log_format.py`)
- `tests/test_log_format.py` — parameterized renamed test file
- `tests/test_voice_wake_word.py` — smoke tests for `WakeWordDetector.reset()` and `process_with_score()`

**Modified:**
- `src/voice/wake_word.py` — add `reset()`, add `process_with_score()` sibling
- `src/core/classifier/multilabel_classifier.py` — PR mode loads both catalogs
- `src/core/responder/registry_pr.py` — add `_EVA_FIELD_PATHS`, build `REGISTRY_PR_FULL`
- `src/modes/eva/main.py` — call shared `configure_logging` with EVA tag set
- `src/modes/pr/main.py` — adopt `logging` with PR tag set; three-state mux; cooldown; pass `REGISTRY_PR_FULL`
- `tests/test_registry_pr.py` — assert `REGISTRY_PR_FULL` has 88 entries, spot-check EVA-side labels
- `tests/test_multilabel_classifier.py` — update PR-mask test to expect EVA labels active
- `tests/test_phase2_smoke.py` — add PR-mode end-to-end for an EVA telemetry query; switch `REGISTRY_PR` reference to `REGISTRY_PR_FULL` where dispatched

**Deleted:**
- `src/modes/eva/log_format.py` — superseded by `src/core/log_format.py`
- `src/modes/pr/log_helpers.py` — superseded by `logging`
- `tests/test_eva_log_format.py` — replaced by `tests/test_log_format.py`

---

# GROUP A — Logging port

Refactor only; behavior-preserving. Lands first so the rest of the work uses the shared logging surface.

## Task A1: Create shared `src/core/log_format.py`

**Files:**
- Create: `src/core/log_format.py`
- Create: `tests/test_log_format.py`

- [ ] **Step 1: Create the new test file with parameterized fixtures**

Write `tests/test_log_format.py`:

```python
import logging

import pytest

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
```

- [ ] **Step 2: Run the test file — it must fail because the module does not exist yet**

Run: `uv run pytest tests/test_log_format.py -v`
Expected: `ModuleNotFoundError: No module named 'src.core.log_format'`

- [ ] **Step 3: Create `src/core/log_format.py`**

```python
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
```

- [ ] **Step 4: Run the new tests — they should pass**

Run: `uv run pytest tests/test_log_format.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/core/log_format.py tests/test_log_format.py
git commit -m "feat(core): add shared parameterized log formatter

Lift EVA's color formatter to src/core/log_format.py with an
event_tags + event_colors + level_env_var signature so both modes can
share it. Tag taxonomies stay per-mode. Behavior identical to the
existing EvaColorFormatter on EVA's tag set.
"
```

---

## Task A2: Migrate EVA mode to shared formatter

**Files:**
- Modify: `src/modes/eva/main.py`
- Delete: `src/modes/eva/log_format.py`
- Delete: `tests/test_eva_log_format.py`

- [ ] **Step 1: Edit `src/modes/eva/main.py` to call shared module**

Replace the import line:

```python
from src.modes.eva.log_format import configure_eva_logging
```

with:

```python
from src.core.log_format import CYAN, DIM_GREY, GREEN, MAGENTA, YELLOW, configure_logging

EVA_EVENT_TAGS = {
    "mic":    "[MIC]    ",
    "vad":    "[VAD]    ",
    "stt":    "[STT]    ",
    "intent": "[INTENT] ",
    "reply":  "[REPLY]  ",
}
EVA_EVENT_COLORS = {
    "mic":    CYAN,
    "vad":    DIM_GREY,
    "stt":    GREEN,
    "intent": YELLOW,
    "reply":  MAGENTA,
}
```

Replace the call inside `start_server()`:

```python
configure_eva_logging()
```

with:

```python
configure_logging(
    event_tags=EVA_EVENT_TAGS,
    event_colors=EVA_EVENT_COLORS,
    level_env_var="EVA_LOG_LEVEL",
)
```

- [ ] **Step 2: Delete the old EVA-only formatter and its test**

```bash
rm src/modes/eva/log_format.py tests/test_eva_log_format.py
```

- [ ] **Step 3: Run the EVA test suite to confirm no regression**

Run: `uv run pytest tests/test_eva_session.py tests/test_eva_protocol.py tests/test_eva_handler_e2e.py tests/test_log_format.py -v`
Expected: All tests PASS. (EVA session/protocol/handler tests don't import the formatter directly; they use logging and were unaffected by the EvaColorFormatter installation.)

- [ ] **Step 4: Smoke-check that EVA mode boots**

Run: `uv run python -c "from src.modes.eva.main import start_server; print('import OK')"`
Expected: `import OK` printed; no `ModuleNotFoundError`.

- [ ] **Step 5: Commit**

```bash
git add -A src/modes/eva/main.py src/modes/eva/log_format.py tests/test_eva_log_format.py
git commit -m "refactor(eva): use shared configure_logging from src.core.log_format

EVA tag set + colors now live next to the entry point in src/modes/eva/main.py.
EvaColorFormatter and configure_eva_logging deleted; the legacy
test_eva_log_format.py is replaced by tests/test_log_format.py.
"
```

---

## Task A3: Migrate PR mode to logging with event tags

**Files:**
- Modify: `src/modes/pr/main.py`
- Delete: `src/modes/pr/log_helpers.py`

- [ ] **Step 1: Replace the imports at the top of `src/modes/pr/main.py`**

Remove the `from src.modes.pr.log_helpers import ...` block (lines 26-31).

Add:

```python
from src.core.log_format import CYAN, DIM_GREY, GREEN, MAGENTA, YELLOW, configure_logging

log = logging.getLogger(__name__)

PR_EVENT_TAGS = {
    "wake":   "[WAKE]   ",
    "vad":    "[VAD]    ",
    "stt":    "[STT]    ",
    "intent": "[INTENT] ",
    "reply":  "[REPLY]  ",
    "tts":    "[TTS]    ",
}
PR_EVENT_COLORS = {
    "wake":   CYAN,
    "vad":    DIM_GREY,
    "stt":    GREEN,
    "intent": YELLOW,
    "reply":  MAGENTA,
    "tts":    DIM_GREY,
}
```

- [ ] **Step 2: Replace every log helper call in `start_agent`, `voice_loop`, `text_loop`, and `main`**

In `start_agent`:

```python
# Before:
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log_info("Starting CORVUS-PR Agent…")
log_info(f"Confidence threshold: {CONFIDENCE_THRESH_HIGH}")
log_info(f"Mode: {'text' if text_mode else 'voice'}")
...
log_info(f"TTTDTT client started (target: {TTTDTT_URL})")
...
log_success(f"Classifier loaded ({classifier.__class__.__name__})")
...
log_success("Piper TTS loaded")

# After:
configure_logging(
    event_tags=PR_EVENT_TAGS,
    event_colors=PR_EVENT_COLORS,
    level_env_var="PR_LOG_LEVEL",
)
log.info("Starting CORVUS-PR Agent…")
log.info("Confidence threshold: %s", CONFIDENCE_THRESH_HIGH)
log.info("Mode: %s", "text" if text_mode else "voice")
...
log.info("TTTDTT client started (target: %s)", TTTDTT_URL)
...
log.info("Classifier loaded (%s)", classifier.__class__.__name__)
...
log.info("Piper TTS loaded")
```

In `voice_loop` callback and main body:

```python
# Before:
log_info("Wake word listener active. Say 'hey corvus' to interact.")
...
def callback(indata, frames, time_info, status):
    if status:
        log_warning(f"Audio status: {status}")
...
log_success("Wake word detected.")
log_info("Listening (VAD-gated)…")
...
log_info(f"Heard: {command!r}")
...
log_info(f"[{classification['intent']} @ {classification['confidence']:.2f}] {response_text}")

# After:
log.info("Wake word listener active. Say 'hey corvus' to interact.")
...
def callback(indata, frames, time_info, status):
    if status:
        log.warning("Audio status: %s", status)
...
# Replace wake "detected" log; score comes from process_with_score (Task C1):
log.info("detected", extra={"event": "wake"})
log.info("capturing…", extra={"event": "vad"})
...
log.info("%r", command, extra={"event": "stt"})
...
log.info(
    "%s (conf %.2f)",
    classification["intent"],
    classification["confidence"],
    extra={"event": "intent"},
)
log.info("%s", response_text, extra={"event": "reply"})
```

In `text_loop` (no `[WAKE]` / `[VAD]` / `[TTS]` because the front-end is stdin):

```python
# Before:
log_info("Type a command and press Enter (or 'quit' to exit):")
...
log_info(f"[{classification['intent']} @ {classification['confidence']:.2f}] {response_text}")

# After:
log.info("Type a command and press Enter (or 'quit' to exit):")
...
log.info("%r", command, extra={"event": "stt"})
log.info(
    "%s (conf %.2f)",
    classification["intent"],
    classification["confidence"],
    extra={"event": "intent"},
)
log.info("%s", response_text, extra={"event": "reply"})
```

In `main`:

```python
# Before:
log_info("\nAgent stopped by user (Ctrl+C)")
...
log_error(f"Agent crashed: {exc}")

# After:
log.info("Agent stopped by user (Ctrl+C)")
...
log.exception("Agent crashed")  # exception() includes the traceback
```

- [ ] **Step 3: Delete `src/modes/pr/log_helpers.py`**

```bash
rm src/modes/pr/log_helpers.py
```

- [ ] **Step 4: Confirm no remaining importers**

Run: `git grep -nE 'log_helpers|log_info|log_success|log_warning|log_error' src/`
Expected: zero matches.

- [ ] **Step 5: Smoke-test the PR text loop**

Run: `echo "what is the battery level" | uv run corvus-pr --text 2>&1 | head -30`
Expected: boot lines (INFO src.modes.pr.main: ...), then `[STT]`, `[INTENT]`, `[REPLY]` event-tagged lines. No `[INFO]/[SUCCESS]/[WARNING]/[ERROR]` print-style markers.

(If TTTDTT isn't running, the response will be `Telemetry unavailable right now.` — still proves the log path.)

- [ ] **Step 6: Commit**

```bash
git add -A src/modes/pr/main.py src/modes/pr/log_helpers.py
git commit -m "refactor(pr): migrate PR mode from print helpers to logging

Replace src/modes/pr/log_helpers.py (deleted) with the shared
configure_logging + logger.info(extra={'event': ...}) pattern used by
EVA. PR's tag set adds [WAKE] and [TTS] for the two stages that don't
exist on the EVA side.

Reads PR_LOG_LEVEL (default INFO). Behavior under faster_whisper
silencing matches EVA's startup.
"
```

---

# GROUP B — PR sees EVA data

Additive change. Existing PR behavior is preserved; PR mode gains the ability to answer EVA telemetry queries.

## Task B1: Multilabel mask — PR mode loads both catalogs

**Files:**
- Modify: `src/core/classifier/multilabel_classifier.py`
- Modify: `tests/test_multilabel_classifier.py`

- [ ] **Step 1: Replace the failing PR-mask test with the new expectation**

Open `tests/test_multilabel_classifier.py`. Find `test_pr_mask_zeros_out_eva_labels` (current behavior — PR mask blocks EVA labels) and replace its body with the new expectation — PR mask should include EVA labels:

```python
def test_pr_mask_includes_eva_labels(fake_sidecar_dir, fake_catalogs):
    # Logits favor an EVA label (get_heart_rate_eva1=0). PR mode must NOT
    # zero it out anymore: PR sees both PR and EVA labels.
    logits = torch.tensor([[5.0, 0.1, 1.0, 0.5]])  # idx 0 (EVA) dominates
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="pr",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    result = clf.classify("anything")
    assert result["intent"] == "get_heart_rate_eva1"
```

Add a second test that confirms the EVA mask is still narrow (EVA mode still zeros out PR labels — unchanged behavior on EVA's side):

```python
def test_eva_mask_still_zeros_pr_labels(fake_sidecar_dir, fake_catalogs):
    logits = torch.tensor([[0.0, 0.1, 5.0, 0.0]])  # PR label dominates
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="eva",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    result = clf.classify("anything")
    # idx 0 (sigmoid 0.5) wins because idx 2 is masked to zero.
    assert result["intent"] == "get_heart_rate_eva1"
```

- [ ] **Step 2: Run the tests — `test_pr_mask_includes_eva_labels` must FAIL**

Run: `uv run pytest tests/test_multilabel_classifier.py -v`
Expected: `test_pr_mask_includes_eva_labels` FAILS because the current implementation still loads only `intentPR.json` and masks out EVA labels.

- [ ] **Step 3: Edit `src/core/classifier/multilabel_classifier.py`**

In `MultilabelClassifier.__init__`, replace the single-catalog load (around lines 60-66):

```python
# Before:
catalogs_dir = catalogs_dir or DEFAULT_CATALOGS_DIR
catalog_path = catalogs_dir / ("intenteva.json" if mode == "eva" else "intentPR.json")
catalog = json.loads(Path(catalog_path).read_text())
active_labels = {row["intent"] for row in catalog}
```

with the union load for PR:

```python
catalogs_dir = catalogs_dir or DEFAULT_CATALOGS_DIR
if mode == "pr":
    catalog_paths = [
        catalogs_dir / "intentPR.json",
        catalogs_dir / "intenteva.json",
    ]
else:  # "eva" — unchanged
    catalog_paths = [catalogs_dir / "intenteva.json"]
active_labels: set[str] = set()
for path in catalog_paths:
    active_labels.update(row["intent"] for row in json.loads(Path(path).read_text()))
```

- [ ] **Step 4: Run the tests — they should all pass**

Run: `uv run pytest tests/test_multilabel_classifier.py -v`
Expected: All tests PASS, including the new `test_pr_mask_includes_eva_labels`.

- [ ] **Step 5: Verify the boot log line shows the right active count**

Run: `uv run python -c "
import logging; logging.basicConfig(level=logging.INFO)
from src.core.classifier.multilabel_classifier import MultilabelClassifier
import torch
clf = MultilabelClassifier(
    'models/PR-Model', mode='pr',
    module=type('M', (), {'forward_texts': lambda self, t, d: torch.zeros(1, 88)})(),
)
"`
Expected: log line `MultilabelClassifier ready: mode=pr, 88 active labels of 88, device=cpu, model_dir=models/PR-Model`.

- [ ] **Step 6: Commit**

```bash
git add src/core/classifier/multilabel_classifier.py tests/test_multilabel_classifier.py
git commit -m "feat(classifier): PR mode masks the full PR + EVA label union

MultilabelClassifier(mode='pr') now loads both intent catalogs and
activates all 88 labels. EVA mode is unchanged (still 45 active labels).
The PR-Model checkpoint was already trained on the full 88-label set,
so no retraining is needed.
"
```

---

## Task B2: Extend `REGISTRY_PR` with EVA field-path mappings

**Files:**
- Modify: `src/core/responder/registry_pr.py`
- Modify: `tests/test_registry_pr.py`

- [ ] **Step 1: Add the failing assertions to `tests/test_registry_pr.py`**

At the top of the file, change the import:

```python
# Before:
from src.core.responder.registry_pr import REGISTRY_PR

# After:
from src.core.responder.registry_pr import REGISTRY_PR, REGISTRY_PR_FULL
```

Add new tests at the bottom (do NOT delete the existing 43-entry test on `REGISTRY_PR` — that still asserts the PR-only rover registry):

```python
def test_registry_pr_full_has_88_entries():
    assert len(REGISTRY_PR_FULL) == 88


def test_registry_pr_full_includes_every_pr_label():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    missing = labels - set(REGISTRY_PR_FULL)
    assert not missing, f"PR labels missing from REGISTRY_PR_FULL: {sorted(missing)}"


def test_registry_pr_full_includes_every_eva_label():
    eva_catalog = Path(__file__).resolve().parents[1] / "models" / "intent_catalogs" / "intenteva.json"
    if not eva_catalog.exists():
        pytest.skip("EVA catalog not installed")
    labels = {row["intent"] for row in json.loads(eva_catalog.read_text())}
    missing = labels - set(REGISTRY_PR_FULL)
    assert not missing, f"EVA labels missing from REGISTRY_PR_FULL: {sorted(missing)}"


def test_get_heart_rate_eva1_reads_eva_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})
    out = REGISTRY_PR_FULL["get_heart_rate_eva1"](
        "hi", cache, {"intent": "get_heart_rate_eva1", "confidence": 0.9}
    )
    assert "72" in out and "EVA 1" in out and "beats per minute" in out


def test_get_heart_rate_eva2_reads_eva_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})
    out = REGISTRY_PR_FULL["get_heart_rate_eva2"](
        "hi", cache, {"intent": "get_heart_rate_eva2", "confidence": 0.9}
    )
    assert "80" in out and "EVA 2" in out


def test_get_oxy_pri_pressure_eva1_formats_with_psi_and_2dp():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"oxy_pri_pressure": 3.456789}}})
    out = REGISTRY_PR_FULL["get_oxy_pri_pressure_eva1"](
        "hi", cache, {"intent": "get_oxy_pri_pressure_eva1", "confidence": 0.9}
    )
    assert "3.46" in out
    assert "P S I" in out


def test_eva_label_unavailable_when_eva_cache_empty():
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_PR_FULL["get_temperature_eva1"](
        "hi", cache, {"intent": "get_temperature_eva1", "confidence": 0.9}
    )
    from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
    assert out == TELEMETRY_UNAVAILABLE_REPLY
```

- [ ] **Step 2: Run the tests — they should fail**

Run: `uv run pytest tests/test_registry_pr.py -v`
Expected: `ImportError: cannot import name 'REGISTRY_PR_FULL' from 'src.core.responder.registry_pr'`.

- [ ] **Step 3: Edit `src/core/responder/registry_pr.py`**

Append the EVA field-path table and the merged registry at the bottom (keep the existing `REGISTRY_PR` definition and its 43-entry assertion untouched):

```python
# ---------------------------------------------------------------------------
# Phase 3: PR mode answers EVA-side telemetry queries too. We bolt the 45 EVA
# labels onto the 43 PR labels via the existing template_handler factory.
# Mapping pattern: get_<field>_eva{N} → telemetry.eva{N}.<field>; three
# asymmetric labels listed explicitly.
# ---------------------------------------------------------------------------
_EVA_FIELD_PATHS: dict[str, str] = {
    "get_heart_rate_eva1":               "telemetry.eva1.heart_rate",
    "get_heart_rate_eva2":               "telemetry.eva2.heart_rate",
    "get_temperature_eva1":              "telemetry.eva1.temperature",
    "get_temperature_eva2":              "telemetry.eva2.temperature",
    "get_oxy_pri_storage_eva1":          "telemetry.eva1.oxy_pri_storage",
    "get_oxy_pri_storage_eva2":          "telemetry.eva2.oxy_pri_storage",
    "get_oxy_sec_storage_eva1":          "telemetry.eva1.oxy_sec_storage",
    "get_oxy_sec_storage_eva2":          "telemetry.eva2.oxy_sec_storage",
    "get_oxy_pri_pressure_eva1":         "telemetry.eva1.oxy_pri_pressure",
    "get_oxy_pri_pressure_eva2":         "telemetry.eva2.oxy_pri_pressure",
    "get_oxy_sec_pressure_eva1":         "telemetry.eva1.oxy_sec_pressure",
    "get_oxy_sec_pressure_eva2":         "telemetry.eva2.oxy_sec_pressure",
    "get_suit_pressure_oxy_eva1":        "telemetry.eva1.suit_pressure_oxy",
    "get_suit_pressure_oxy_eva2":        "telemetry.eva2.suit_pressure_oxy",
    "get_suit_pressure_co2_eva1":        "telemetry.eva1.suit_pressure_co2",
    "get_suit_pressure_co2_eva2":        "telemetry.eva2.suit_pressure_co2",
    "get_suit_pressure_other_eva1":      "telemetry.eva1.suit_pressure_other",
    "get_suit_pressure_other_eva2":      "telemetry.eva2.suit_pressure_other",
    "get_suit_pressure_total_eva1":      "telemetry.eva1.suit_pressure_total",
    "get_suit_pressure_total_eva2":      "telemetry.eva2.suit_pressure_total",
    "get_helmet_pressure_co2_eva1":      "telemetry.eva1.helmet_pressure_co2",
    "get_helmet_pressure_co2_eva2":      "telemetry.eva2.helmet_pressure_co2",
    "get_fan_pri_rpm_eva1":              "telemetry.eva1.fan_pri_rpm",
    "get_fan_pri_rpm_eva2":              "telemetry.eva2.fan_pri_rpm",
    "get_fan_sec_rpm_eva1":              "telemetry.eva1.fan_sec_rpm",
    "get_fan_sec_rpm_eva2":              "telemetry.eva2.fan_sec_rpm",
    "get_scrubber_a_co2_storage_eva1":   "telemetry.eva1.scrubber_a_co2_storage",
    "get_scrubber_a_co2_storage_eva2":   "telemetry.eva2.scrubber_a_co2_storage",
    "get_scrubber_b_co2_storage_eva1":   "telemetry.eva1.scrubber_b_co2_storage",
    "get_scrubber_b_co2_storage_eva2":   "telemetry.eva2.scrubber_b_co2_storage",
    "get_coolant_storage_eva1":          "telemetry.eva1.coolant_storage",
    "get_coolant_storage_eva2":          "telemetry.eva2.coolant_storage",
    "get_coolant_gas_pressure_eva1":     "telemetry.eva1.coolant_gas_pressure",
    "get_coolant_gas_pressure_eva2":     "telemetry.eva2.coolant_gas_pressure",
    "get_coolant_liquid_pressure_eva1":  "telemetry.eva1.coolant_liquid_pressure",
    "get_coolant_liquid_pressure_eva2":  "telemetry.eva2.coolant_liquid_pressure",
    "get_oxy_consumption_eva1":          "telemetry.eva1.oxy_consumption",
    "get_oxy_consumption_eva2":          "telemetry.eva2.oxy_consumption",
    "get_co2_production_eva1":           "telemetry.eva1.co2_production",
    "get_co2_production_eva2":           "telemetry.eva2.co2_production",
    "get_eva_elapsed_time_eva1":         "telemetry.eva1.eva_elapsed_time",
    "get_eva_elapsed_time_eva2":         "telemetry.eva2.eva_elapsed_time",
    "get_battery_level_eva2":            "telemetry.eva2.battery_level",
    "get_primary_battery_level_eva1":    "telemetry.eva1.primary_battery_level",
    "get_secondary_battery_level_eva1":  "telemetry.eva1.secondary_battery_level",
}


REGISTRY_PR_FULL: dict[str, ResponseFn] = {
    **REGISTRY_PR,
    **{label: template_handler(label, "eva", path)
       for label, path in _EVA_FIELD_PATHS.items()},
}

assert len(REGISTRY_PR_FULL) == 88, (
    f"REGISTRY_PR_FULL should have 88 entries (43 PR + 45 EVA), got {len(REGISTRY_PR_FULL)}"
)
```

- [ ] **Step 4: Run the registry tests**

Run: `uv run pytest tests/test_registry_pr.py -v`
Expected: All tests PASS — including the 6 new ones plus the existing 43-entry assertion on `REGISTRY_PR`.

- [ ] **Step 5: Verify templates and 2dp formatting work for EVA labels**

Run: `uv run python -c "
from src.core.responder.registry_pr import REGISTRY_PR_FULL
from src.core.telemetry.cache import TelemetryCache
cache = TelemetryCache(stale_after_s=10.0)
cache.put('eva', {'telemetry': {'eva1': {'heart_rate': 72.3456}, 'eva2': {'oxy_pri_pressure': 3.14159}}})
print(REGISTRY_PR_FULL['get_heart_rate_eva1']('q', cache, {'intent':'get_heart_rate_eva1','confidence':0.9}))
print(REGISTRY_PR_FULL['get_oxy_pri_pressure_eva2']('q', cache, {'intent':'get_oxy_pri_pressure_eva2','confidence':0.9}))
"`
Expected:
```
The heart rate for EVA 1 is 72.35 beats per minute.
The primary oxygen pressure for EVA 2 is 3.14 P S I.
```

- [ ] **Step 6: Commit**

```bash
git add src/core/responder/registry_pr.py tests/test_registry_pr.py
git commit -m "feat(responder): expand PR registry to cover all 88 multilabel intents

Add _EVA_FIELD_PATHS (45 entries: 42 symmetric eva1/eva2 reads + 3
asymmetric battery labels) and build REGISTRY_PR_FULL = REGISTRY_PR
| eva_handlers via the existing template_handler factory. All 45
templates already exist in INTENT_RESPONSE_TEMPLATES with spelled-out
units; _format_value applies 2dp float formatting automatically.

The original 43-entry REGISTRY_PR remains for tests that want the
PR-only set in isolation.
"
```

---

## Task B3: Wire `REGISTRY_PR_FULL` into PR main + smoke test

**Files:**
- Modify: `src/modes/pr/main.py`
- Modify: `tests/test_phase2_smoke.py`

- [ ] **Step 1: Add the failing smoke test**

In `tests/test_phase2_smoke.py`, at the top change:

```python
from src.core.responder.registry_pr import REGISTRY_PR
```

to:

```python
from src.core.responder.registry_pr import REGISTRY_PR, REGISTRY_PR_FULL
```

Update the existing `test_pr_pipeline_canonical_battery` and `test_pr_pipeline_set_lights_on_verbal_ack` so they dispatch against `REGISTRY_PR_FULL` (drop-in replacement; `REGISTRY_PR_FULL` is a superset).

Then add the new EVA-from-PR end-to-end test:

```python
@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_eva_heart_rate(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})

    classification = pr_clf.classify("what is eva 1 heart rate")
    assert classification["intent"] == "get_heart_rate_eva1", classification
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert "72" in response
    assert "EVA 1" in response
    assert "beats per minute" in response


@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_eva_label_unavailable_when_eva_cache_empty(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    classification = pr_clf.classify("what is eva 1 heart rate")
    assert classification["intent"] == "get_heart_rate_eva1"
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert response == TELEMETRY_UNAVAILABLE_REPLY
```

- [ ] **Step 2: Run the smoke tests — they should fail because PR main still passes the 43-entry `REGISTRY_PR`**

Run: `uv run pytest tests/test_phase2_smoke.py -v`
Expected: `test_pr_pipeline_eva_heart_rate` passes if model classifies correctly, FAILS at `assert classification["intent"] == "get_heart_rate_eva1"` if the mask isn't picking it up (regression check on Task B1 — should be picking it up).

If both new tests pass at this stage, that's fine — it means the multilabel + registry wiring is already there from B1 and B2. Move on.

- [ ] **Step 3: Edit `src/modes/pr/main.py` to import and pass `REGISTRY_PR_FULL`**

Replace:

```python
from src.core.responder.registry_pr import REGISTRY_PR
```

with:

```python
from src.core.responder.registry_pr import REGISTRY_PR_FULL
```

Replace both `dispatch.respond(command, classification, cache, REGISTRY_PR)` call sites (in `voice_loop` and `text_loop`) with:

```python
dispatch.respond(command, classification, cache, REGISTRY_PR_FULL)
```

- [ ] **Step 4: Re-run the smoke test**

Run: `uv run pytest tests/test_phase2_smoke.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Manual smoke via the text loop**

Run: `printf "what is eva 1 heart rate\nquit\n" | uv run corvus-pr --text 2>&1 | grep -E '\[(INTENT|REPLY)\]'`
Expected (when TTTDTT has no EVA telemetry yet):
```
[INTENT] get_heart_rate_eva1 (conf 0.xx)
[REPLY]  Telemetry unavailable right now.
```
If TTTDTT IS publishing the eva channel with `telemetry.eva1.heart_rate`, the reply line shows the formatted heart rate instead.

- [ ] **Step 6: Commit**

```bash
git add src/modes/pr/main.py tests/test_phase2_smoke.py
git commit -m "feat(pr): dispatch against REGISTRY_PR_FULL so PR answers EVA queries

PR mode now hands the full 88-entry registry to dispatch.respond. The
existing 43 rover responses are unchanged; the 45 EVA telemetry intents
are answered against the 'eva' channel populated by TelemetryClient.

Adds end-to-end smoke for 'what is eva 1 heart rate' returning a
2dp-formatted '72.00 beats per minute' response.
"
```

---

# GROUP C — Wake-word re-fire fix

Isolated to PR voice loop. `--text` mode is unaffected.

## Task C1: Add `reset()` and `process_with_score()` to `WakeWordDetector`

**Files:**
- Modify: `src/voice/wake_word.py`
- Create: `tests/test_voice_wake_word.py`

- [ ] **Step 1: Verify openWakeWord 0.6 exposes a reset path**

Run: `uv run python -c "
from openwakeword.model import Model
print('reset method:', hasattr(Model, 'reset'))
print('reset_states method:', hasattr(Model, 'reset_states'))
import inspect; print([n for n in dir(Model) if 'reset' in n.lower() or 'clear' in n.lower()])
"`
Expected: at least one of `reset` / `reset_states` is True, or the inspect list shows a callable that wipes the rolling buffers. If neither is present, the fallback in Step 4 (re-instantiate Model) applies.

- [ ] **Step 2: Write the wake-word smoke tests**

Create `tests/test_voice_wake_word.py`:

```python
"""Smoke tests for WakeWordDetector. The actual openWakeWord Model is
loaded once and we exercise reset() + process_with_score() against it.
"""

from pathlib import Path

import numpy as np
import pytest

WAKE_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "wake_word" / "hey_corvus.onnx"
MELSPEC_PATH = Path(__file__).resolve().parents[1] / "models" / "openwakeword" / "melspectrogram.onnx"


def _wake_assets_present() -> bool:
    return WAKE_MODEL_PATH.exists() and MELSPEC_PATH.exists()


requires_wake_assets = pytest.mark.skipif(
    not _wake_assets_present(),
    reason="wake-word ONNX assets not installed",
)


@pytest.fixture
def detector():
    from src.voice.wake_word import WakeWordDetector
    return WakeWordDetector(model_paths=[str(WAKE_MODEL_PATH)])


@requires_wake_assets
def test_reset_is_callable_without_raising(detector):
    detector.reset()  # idempotent + must not throw


@requires_wake_assets
def test_process_with_score_returns_tuple(detector):
    silence = np.zeros(1280, dtype=np.float32)
    triggered, score = detector.process_with_score(silence)
    assert isinstance(triggered, bool)
    assert isinstance(score, float)
    # Silence should not trigger; score is some real number, possibly small.
    assert not triggered


@requires_wake_assets
def test_process_with_score_int16_input_accepted(detector):
    silence = np.zeros(1280, dtype=np.int16)
    triggered, score = detector.process_with_score(silence)
    assert isinstance(triggered, bool)
    assert isinstance(score, float)


@requires_wake_assets
def test_process_back_compat_returns_bool(detector):
    silence = np.zeros(1280, dtype=np.float32)
    triggered = detector.process(silence)
    assert isinstance(triggered, bool)
```

- [ ] **Step 3: Run the new tests — they should fail because the methods don't exist yet**

Run: `uv run pytest tests/test_voice_wake_word.py -v`
Expected: `AttributeError: 'WakeWordDetector' object has no attribute 'reset'` (or `process_with_score`).

- [ ] **Step 4: Edit `src/voice/wake_word.py` — add the two methods**

Append the two methods to the `WakeWordDetector` class (after the existing `process`). Use openWakeWord's `reset` if available; otherwise reload the underlying Model with the cached arguments.

```python
class WakeWordDetector:
    def __init__(self, wakewords=None, model_paths=None, threshold=0.5):
        from openwakeword.model import Model
        if model_paths is None:
            paths = _resolve_wakeword_paths(wakewords or DEFAULT_WAKEWORD)
        else:
            paths = model_paths
        log.info("Loading openWakeWord with %d model(s)", len(paths))
        if not MELSPEC_PATH.is_file() or not EMBEDDING_PATH.is_file():
            raise FileNotFoundError(...)
        self._paths = paths            # NEW: cache for reload-fallback
        self._threshold = threshold
        self._model = Model(
            wakeword_models=paths,
            melspec_model_path=str(MELSPEC_PATH),
            embedding_model_path=str(EMBEDDING_PATH),
        )

    def process(self, audio_chunk):
        triggered, _score = self.process_with_score(audio_chunk)
        return triggered

    def process_with_score(self, audio_chunk):
        """audio_chunk: float32 or int16 mono 16 kHz. Returns
        (triggered, max_score) so callers can log the fire score."""
        if audio_chunk.dtype != np.int16:
            audio_chunk = (audio_chunk * 32767.0).clip(-32768, 32767).astype(np.int16)
        scores = self._model.predict(audio_chunk)
        max_score = max(scores.values()) if scores else 0.0
        return (max_score >= self._threshold, float(max_score))

    def reset(self) -> None:
        """Wipe openWakeWord's internal rolling buffer so a fresh
        utterance doesn't activate against stale audio."""
        reset_fn = getattr(self._model, "reset", None) or getattr(self._model, "reset_states", None)
        if callable(reset_fn):
            reset_fn()
            return
        # Fallback: re-instantiate the model with cached paths. Slower
        # (~100 ms) but always correct.
        from openwakeword.model import Model
        self._model = Model(
            wakeword_models=self._paths,
            melspec_model_path=str(MELSPEC_PATH),
            embedding_model_path=str(EMBEDDING_PATH),
        )
```

(Keep the existing `__init__` signature; just add `self._paths = paths` and use the new helpers below it. `process` becomes a thin wrapper that discards the score.)

- [ ] **Step 5: Run the wake-word tests — they should pass**

Run: `uv run pytest tests/test_voice_wake_word.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/voice/wake_word.py tests/test_voice_wake_word.py
git commit -m "feat(voice): add WakeWordDetector.reset and process_with_score

reset() clears openWakeWord's internal rolling buffers (uses Model.reset
when available; falls back to a Model reload). process_with_score()
returns (triggered, max_score) so the PR voice loop can log the fire
score in its [WAKE] event line. process() stays bool for back-compat.
"
```

---

## Task C2: Three-state audio mux + cooldown in PR voice loop

**Files:**
- Modify: `src/modes/pr/main.py`

- [ ] **Step 1: Add the cooldown constant near the other constants**

Open `src/modes/pr/main.py`. Below `MAX_CAPTURE_S = 8.0` and above `WAKE_MODEL_PATH = ...`, add:

```python
WAKE_COOLDOWN_S = 0.3   # ignore wake fires for this long after playback ends
```

- [ ] **Step 2: Add `time` to the imports near the top**

```python
import time
```

- [ ] **Step 3: Modify the callback inside `voice_loop` to handle `playback` mode and cooldown**

Replace the callback (currently lines 84-92) with:

```python
state = {"mode": "wake"}        # 'wake' | 'capture' | 'playback'
wake_cooldown_until = {"deadline": 0.0}   # mutable holder so callback can read
last_wake_score = {"value": 0.0}          # ditto, for the [WAKE] log line

def callback(indata, frames, time_info, status):
    if status:
        log.warning("Audio status: %s", status)
    if state["mode"] == "playback":
        return                  # mic is muted while Piper speaks
    chunk = (indata[:, 0] if indata.ndim > 1 else indata).astype(np.float32, copy=True)
    if state["mode"] == "wake":
        if time.monotonic() < wake_cooldown_until["deadline"]:
            return              # cooldown: drop wake input briefly
        triggered, score = wake.process_with_score(chunk)
        if triggered:
            last_wake_score["value"] = score
            main_loop.call_soon_threadsafe(wake_triggered.set)
    else:                        # capture
        main_loop.call_soon_threadsafe(capture_queue.put_nowait, chunk)
```

- [ ] **Step 4: Update the main `voice_loop` body to flip into `playback` and reset on the way out**

Replace the wake-triggered block + dispatch block (currently lines 95-119) with:

```python
with open_input_stream(callback, blocksize=WAKEWORD_BLOCK_SAMPLES):
    while True:
        await wake_triggered.wait()
        wake_triggered.clear()
        log.info(
            "detected (score %.2f)",
            last_wake_score["value"],
            extra={"event": "wake"},
        )
        log.info("capturing…", extra={"event": "vad"})

        while not capture_queue.empty():
            capture_queue.get_nowait()
        state["mode"] = "capture"
        try:
            audio = await capture_utterance(capture_queue, vad)
        finally:
            state["mode"] = "wake"  # provisional; re-flipped below on playback path

        command = await main_loop.run_in_executor(None, lambda: stt.transcribe(audio))
        log.info("%r", command, extra={"event": "stt"})

        if not command:
            continue
        classification = classifier.classify(command)
        response_text = dispatch.respond(command, classification, cache, REGISTRY_PR_FULL)
        log.info(
            "%s (conf %.2f)",
            classification["intent"],
            classification["confidence"],
            extra={"event": "intent"},
        )
        log.info("%s", response_text, extra={"event": "reply"})

        audio_out = await main_loop.run_in_executor(None, lambda: tts.synthesize(response_text))
        playback_duration_s = len(audio_out) / float(tts.sample_rate) if len(audio_out) else 0.0
        log.info("speaking %.1fs", playback_duration_s, extra={"event": "tts"})

        state["mode"] = "playback"
        try:
            await main_loop.run_in_executor(None, lambda: play_blocking(audio_out, tts.sample_rate))
        finally:
            wake.reset()
            wake_cooldown_until["deadline"] = time.monotonic() + WAKE_COOLDOWN_S
            state["mode"] = "wake"
```

(Notes: `last_wake_score` and `wake_cooldown_until` are dicts so the closure can mutate them across threads safely without `nonlocal` gymnastics. We already have `REGISTRY_PR_FULL` imported from Task B3.)

- [ ] **Step 4b: Sanity-check the file**

Run: `uv run python -c "from src.modes.pr import main as m; print('import OK')"`
Expected: `import OK`.

- [ ] **Step 5: Manual acceptance — 10 single utterances, count wake fires**

This step requires a working mic + the local voice stack. Skip if running in CI.

Run: `uv run corvus-pr 2>&1 | tee /tmp/pr-wake-acceptance.log`
Then: say "hey corvus, what is the battery level" ten times in a row, with ~5 s between attempts. Wait for each Piper reply to finish before speaking again.

After: `grep -c '\[WAKE\]' /tmp/pr-wake-acceptance.log`
Expected: exactly 10 (one [WAKE] per utterance — no re-fires).

- [ ] **Step 6: Commit**

```bash
git add src/modes/pr/main.py
git commit -m "fix(pr): eliminate wake-word re-fires with three-state audio mux

Add 'playback' as a third audio-callback mode alongside 'wake' and
'capture'. The mic is muted during Piper playback, the wake-word
state is reset on the playback->wake transition, and a 300 ms cooldown
ignores any echo tail. Defensive against all three observed re-fire
causes (mic picks up TTS, stale wake buffer, hardware echo).

Also tags the new [WAKE] / [TTS] event log lines and logs the wake
score from process_with_score.
"
```

---

# Final verification

- [ ] **Run the full test suite**

Run: `uv run pytest -q`
Expected: All tests PASS or are skipped with documented reasons (missing model bundles on CI). No new failures.

- [ ] **Run the type checker if configured**

Run: `uv run python -m mypy src/ 2>&1 | tail -20` (skip if mypy isn't part of the project setup)

- [ ] **Verify EVA mode still boots correctly**

Run: `EVA_LOG_LEVEL=INFO uv run corvus-eva 2>&1 | head -10 &`
Then: `sleep 3 && pkill -f corvus-eva`
Expected: log lines show `INFO src.modes.eva.main: Starting CORVUS-EVA Server...`, the classifier loads, the websocket binds; no `[INFO]/[SUCCESS]` print markers.

- [ ] **Verify PR mode text loop still works**

Run: `printf "what is the rover battery level\nquit\n" | PR_LOG_LEVEL=INFO uv run corvus-pr --text 2>&1`
Expected: boot lines + `[STT] 'what is the rover battery level'` + `[INTENT] Get_battery_level (conf …)` + `[REPLY] The rover battery level is …` (or `Telemetry unavailable right now.` if TTTDTT isn't running).

- [ ] **Verify PR mode voice loop boots without crashing**

Run: `uv run corvus-pr 2>&1 | head -15 &`
Then: `sleep 5 && pkill -f corvus-pr`
Expected: all three loaders log success (`Whisper STT loaded`, `Silero VAD loaded`, `openWakeWord loaded`); the wake listener banner appears; no traceback.

---

# Spec coverage check

| Spec section | Covered by |
|---|---|
| §3.1 Shared formatter | A1 |
| §3.2 PR event taxonomy | A3 |
| §3.3 PR call-site migration | A3 |
| §3.4 EVA migration | A2 |
| §3.5 Files deleted | A2 + A3 |
| §3.6 Tests (parameterized) | A1 |
| §4.1 WakeWordDetector.reset() + process_with_score() | C1 |
| §4.2 Three-state mux | C2 |
| §4.3 Loop-level transitions | C2 |
| §4.4 Defensive rationale | (design doc, no code) |
| §4.5 Tests | C1 (smoke) + C2 (manual acceptance) |
| §5.1 Mask change | B1 |
| §5.2 _EVA_FIELD_PATHS table | B2 |
| §5.3 Build REGISTRY_PR_FULL | B2 |
| §5.4 Wire into PR main | B3 |
| §5.5 Units & 2dp | B2 (templates + format already correct, asserted by tests) |
| §5.6 Risk surface (cache-miss fallback) | B2 (`test_eva_label_unavailable_when_eva_cache_empty`) |
| §5.7 Tests | B1 + B2 + B3 |
| §6 File-level change summary | File structure section above |
| §7 Rollout order | Group ordering (A → B → C) |
| §8 Out of scope | (no code; explicit non-goals) |
