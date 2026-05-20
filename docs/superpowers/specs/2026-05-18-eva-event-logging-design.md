# EVA Event-Style Logging — Design

**Date:** 2026-05-18
**Scope:** EVA mode only. PR mode logging is unchanged.

## Motivation

The current EVA log output is hard to scan in real time. Two reasons:

1. Two logging paths fight each other. `src/modes/eva/session.py` uses Python
   `logging` (timestamped `INFO/WARNING` lines). `src/modes/eva/websocket_handler.py`
   uses `print()` with hardcoded ANSI escapes (`[INFO]`, `[RESPONSE]`, etc.).
2. The `eva: dropping N bytes received in IDLE state` line spams the console
   every 100 ms while Unity continues streaming audio after the server-side
   VAD has already decided end-of-speech. It is real signal, but at INFO level
   it drowns out the per-turn events that matter.

The user wants a live-watching experience where each turn is five clearly
labelled, color-coded events: mic open, VAD stopped, STT transcript,
classified intent, response.

## Goals

- One log line per meaningful per-turn event, color-coded by event type.
- Default log output contains *only* the five turn events plus connection
  lifecycle. All other diagnostics are recoverable via `EVA_LOG_LEVEL=DEBUG`.
- One logging path. No more `print()` + ANSI in the WebSocket handler.
- Colors auto-disable when stdout/stderr is not a TTY (pipes, redirects,
  log files).

## Non-goals

- PR-mode logging is out of scope. PR keeps its current behavior.
- No external dependency (no `colorama`, no `rich`). Hand-rolled ANSI.
- No structured log shipping (JSON, syslog, etc.). Plain text only.

## Architecture

A single new module, `src/modes/eva/log_format.py`, exports:

- `EvaColorFormatter(logging.Formatter)` — the formatter described below.
- `configure_eva_logging() -> None` — installs a `StreamHandler` on the root
  logger with `EvaColorFormatter`, reads `EVA_LOG_LEVEL` (default `INFO`),
  and demotes the `faster_whisper` logger to DEBUG.

`configure_eva_logging()` is called exactly once, from
`src/modes/eva/main.py`, before any other module logs.

### Formatter behavior

Color decision is made once at module import: `sys.stderr.isatty()`. When
false, every color sequence in the formatter is replaced with the empty
string. No runtime branching.

Records carry an optional `event` field via `logging.Logger.info(..., extra={"event": "stt"})`.
The formatter inspects this:

- If `event` is set, render as `[EVENT_TAG] message` with the
  event-specific color. The standard `levelname`, `asctime`, and `name`
  prefix is suppressed for these records.
- If `event` is unset, render with a compact `%(levelname)s %(name)s: %(message)s`
  format, lightly colored by level (WARNING yellow, ERROR red, INFO/DEBUG
  uncolored). Connection lifecycle (handler messages from
  `websocket_handler`) falls under this path.

ANSI codes used (hand-rolled, no library):

| Color | Code |
|---|---|
| cyan | `\033[96m` |
| green | `\033[92m` |
| yellow | `\033[93m` |
| red | `\033[91m` |
| magenta | `\033[95m` |
| dim grey | `\033[90m` |
| reset | `\033[0m` |

### Configuration knob

| Env var | Default | Effect |
|---|---|---|
| `EVA_LOG_LEVEL` | `INFO` | Standard Python level names. `DEBUG` recovers all demoted lines. |

## The five turn events

| Tag | Color | Trigger site | Line shape |
|---|---|---|---|
| `[MIC]` | cyan | `src/modes/eva/session.py::_handle_start` (after sample-rate validation passes) | `[MIC]    Unity opened mic (16000 Hz mono)` |
| `[VAD]` | dim grey | `src/modes/eva/session.py::_end_of_speech` | `[VAD]    speech ended (2.4s captured)` — duration = `len(self._buffer) / 32000` rounded to 1 dp |
| `[STT]` | green | `src/modes/eva/session.py::finalize`, after `stt.transcribe` returns successfully | `[STT]    "What's the secondary battery level?"` — full transcript, no truncation, `%r`-quoted |
| `[INTENT]` | yellow normally, **red** when `intent == "unhandled"` | `src/modes/eva/session.py::finalize`, immediately after the existing `intent = …` assignment | `[INTENT] vitals_heart_rate (conf 0.964)` |
| `[REPLY]` | magenta | `src/modes/eva/session.py::finalize`, immediately before the `return FinalMsg(...)` | `[REPLY]  The heart rate is 151.1 beats per minute.` |

Two-space padding after the tag aligns the message columns at the cost of
one extra space after `[VAD]` / `[MIC]` / `[STT]`. Acceptable.

The INTENT red-path condition matches the existing gate at
`session.py:194`:

```python
intent = raw_intent if (confidence >= CONFIDENCE_THRESH_HIGH and raw_intent in self.registry) else "unhandled"
```

### Call site vs. formatter contract

The **call site is responsible for the full message string** (e.g.
`f"{intent} (conf {confidence:.3f})"`). The **formatter handles only the
tag, the color, and stripping the standard level/timestamp prefix**.

`extra` carries at most two fields:

- `event`: one of `"mic"`, `"vad"`, `"stt"`, `"intent"`, `"reply"`.
  Selects the tag and base color.
- `intent_unhandled` (only on `event="intent"`): bool. When true, overrides
  the base yellow with red.

Any future event-specific styling (e.g. dim grey for VAD when buffer was
very short) is added the same way: a new boolean field in `extra`,
interpreted by the formatter.

## Disposition of every existing log line

| Current line | New behavior |
|---|---|
| `eva: state IDLE -> BUFFERING` (`session.py:102`) | Removed. Replaced by `[MIC]` event. |
| `eva: state BUFFERING -> IDLE (end-of-speech, N bytes)` (`session.py:168`) | Removed. Replaced by `[VAD]` event. |
| `eva: state BUFFERING -> IDLE (stop received)` (`session.py:109`) | Kept at INFO with current wording. Rare path; only fires on explicit client stop. |
| `eva: dropping N bytes received in IDLE state` (`session.py:120`) | Demoted to DEBUG. |
| `eva: high latency Nms (threshold 500ms)` (`session.py:208`) | Demoted to DEBUG. |
| `eva: final intent=… confidence=… latency_ms=… transcript=…` (`session.py:216`) | Demoted to DEBUG. Kept as the grep-friendly one-line correlation when debugging. |
| `eva: rejecting start (sample_rate=…)` (`session.py:94`) | Kept at WARNING. |
| `eva: odd-length PCM frame …` (`session.py:124`) | Kept at WARNING. |
| `eva: buffer cap … exceeded` (`session.py:159`) | Kept at WARNING. |
| `eva: VAD raised; forcing end-of-speech` (`session.py:143`) | Kept at ERROR via `log.exception`. |
| `eva: STT failed …` / `classifier failed …` / `responder failed …` (`session.py:177-199`) | Kept at ERROR via `log.exception`. |
| `eva: voiceString emit failed; continuing` (`session.py:214`) | Kept at WARNING. |
| `faster_whisper: Processing audio with duration …` | Demoted to DEBUG via `logging.getLogger("faster_whisper").setLevel(DEBUG)` in `configure_eva_logging`. |
| `[SUCCESS] Client connected: …` (`websocket_handler.py:46`) | Migrated to `logger.info`. Rendered green by formatter as a level-based color, no event tag. |
| `[WARNING] Client disconnected: …` (`websocket_handler.py:66`) | Migrated to `logger.warning`. |
| `[ERROR] Error handling client …` (`websocket_handler.py:68`) | Migrated to `logger.error`. |
| `[INFO] Connection closed: …` (`websocket_handler.py:71`) | Migrated to `logger.info`. |
| `[INFO] Starting CORVUS-EVA WebSocket Server…` etc. (`websocket_handler.py:77-85`) | Migrated to `logger.info`. |
| `[RESPONSE]` line in `websocket_handler.py:62` | Removed. The `[REPLY]` event from `session.py` already covers this. |

## File-level change set

1. **New:** `src/modes/eva/log_format.py` (~80 lines).
2. **Modified:** `src/modes/eva/main.py` — add a top-of-`main()`
   `configure_eva_logging()` call.
3. **Modified:** `src/modes/eva/session.py` — emit the five events via
   `log.info(..., extra={"event": ...})`; demote three lines to DEBUG.
4. **Modified:** `src/modes/eva/websocket_handler.py` — delete the `Colors`
   class and `log_*` `print()` helpers, route everything through
   `logger = logging.getLogger(__name__)`. Remove the `log_response()` call
   (REPLY is emitted from session).
5. **New:** `tests/test_eva_log_format.py` — unit tests for the formatter
   (event rendering, TTY vs non-TTY, red-when-unhandled).
6. **Modified, if needed:** existing EVA session tests that may assert on
   log content. Audit during implementation.

## Testing

- **Formatter unit tests** (`tests/test_eva_log_format.py`):
  - Event records render as `[TAG]    message` with no level/timestamp prefix.
  - INTENT renders red when `extra["intent_name"] == "unhandled"`, yellow otherwise.
  - Non-TTY mode (force-disabled via a constructor arg or module patch)
    strips all ANSI codes from output.
  - Non-event records render with `LEVEL name: message`.
- **Session integration test**: existing tests that exercise the
  `EvaSession.finalize` path should keep passing. If any assert on the
  removed `state ... -> ...` INFO lines, update to assert on the new event
  records via `caplog.records`.
- **Manual smoke**: run `uv run corvus-eva`, connect Unity, confirm the
  five-event sequence renders in the expected colors on a TTY and as plain
  text when piped to `tee log.txt`.

## Implementation notes

- **TTY detection happens once at import** of `log_format.py`. Re-evaluating
  per-record would add per-log overhead and `isatty()` does not change
  mid-process under any realistic scenario.
- **Formatter holds no state** beyond the color-enabled boolean. Safe to
  share across handlers.
- **Connection lifecycle lines** (`Client connected`, `disconnected`,
  `Connection closed`, `Server running`) keep their existing wording so
  external monitoring scraping for them still works.
- **`EVA_LOG_LEVEL` parsing** uses `logging.getLevelName(value.upper())`
  with a fallback to INFO on unknown values, logging a single WARNING
  on bad input.
