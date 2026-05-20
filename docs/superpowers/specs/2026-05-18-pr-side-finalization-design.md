# CORVUS PR-side finalization — design

Status: draft
Date: 2026-05-18
Owner: Aaron Sun

## 1. Goals

Three independent improvements to PR mode (`uv run corvus-pr`):

1. **Port EVA's event-tagged logging to PR**, adding `[WAKE]` and `[TTS]` events
   for the two stages PR has that EVA doesn't.
2. **Eliminate wake-word re-fires** after a single utterance. The cause varies
   across sessions, so the fix is defensive: mute the mic during Piper
   playback, reset the wake-word's internal state on transitions, and apply a
   short cooldown.
3. **Let PR mode answer EVA telemetry queries** (heart rate, suit pressure,
   helmet CO2, etc.) in addition to its 43 rover queries. The multilabel
   classifier checkpoint is already trained on all 88 labels — only the
   runtime mask and the response registry need to grow.

Non-goals: changes to EVA mode behavior, changes to the multilabel classifier
checkpoint, changes to TTTDTT wire format.

## 2. Architecture overview

```
┌──────────────────────── PR mode boot ────────────────────────┐
│  configure_logging(event_tags=PR_EVENT_TAGS,                 │
│                    level_env_var="PR_LOG_LEVEL")             │
│      └── shared formatter at src/core/log_format.py          │
│                                                              │
│  TelemetryClient (unchanged) → TelemetryCache                │
│      • rover channel  → pr_telemetry.*                       │
│      • eva   channel  → telemetry.eva1.* / telemetry.eva2.*  │
│                                                              │
│  MultilabelClassifier(mode="pr")                             │
│      mask = union(intentPR.json, intenteva.json) = 88 labels │
│                                                              │
│  REGISTRY_PR_FULL = 88 entries                               │
│      • 43 PR rover handlers (existing)                       │
│      • 45 EVA telemetry handlers (NEW, template-driven)      │
│                                                              │
│  voice_loop with three-state audio mux:                      │
│      wake ←→ capture ←→ playback                             │
│      WakeWordDetector.reset() on playback→wake               │
│      300 ms cooldown after playback→wake                     │
└──────────────────────────────────────────────────────────────┘
```

Each of the three concerns ships as an independent changeset and is testable
in isolation. The order below is the suggested merge order.

## 3. Logging port

### 3.1 New shared module: `src/core/log_format.py`

The current EVA-only formatter at `src/modes/eva/log_format.py` is promoted
to `src/core/log_format.py` and parameterized:

```python
def configure_logging(
    *,
    event_tags: dict[str, str],
    event_colors: dict[str, str],
    level_env_var: str,
) -> None: ...

class ColorFormatter(logging.Formatter): ...  # same body as EvaColorFormatter
```

Behavior is unchanged from the current EvaColorFormatter:

- Event records (`extra={"event": <name>}`) render as `[TAG] <message>` with
  the event's color and no level/timestamp prefix.
- Non-event records render as `LEVEL name: message`, level-colored.
- ANSI auto-disables when stderr is not a TTY.
- Level resolved from `level_env_var` (default `INFO`); when above `DEBUG`,
  the chatty `faster_whisper` logger is pushed to `WARNING`.
- Idempotent: removes existing root handlers before installing.

The `intent_unhandled` red-override for `event="intent"` records is retained.

### 3.2 PR event taxonomy

```python
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

These live in `src/modes/pr/main.py` (alongside the boot code) so that EVA's
tag set in `src/modes/eva/main.py` is symmetric.

### 3.3 PR call-site migration

`src/modes/pr/main.py` replaces every `log_info / log_success / log_warning /
log_error` call with a `logging.getLogger(__name__)` call. Inline status
prints become event-tagged log records:

| Old | New |
|---|---|
| `log_success("Wake word detected.")` | `log.info("detected (score %.2f)", score, extra={"event": "wake"})` |
| `log_info(f"Heard: {command!r}")` | `log.info("%r", command, extra={"event": "stt"})` |
| `log_info(f"[{intent} @ {conf:.2f}] {text}")` | two records: `[INTENT]` + `[REPLY]` matching EVA's format |
| (none — currently silent) | `log.info("speaking %.1fs", duration_s, extra={"event": "tts"})` around `play_blocking` |
| `log_info("Listening (VAD-gated)…")` | `log.info("capturing…", extra={"event": "vad"})` |

`WakeWordDetector.process()` returns `bool`; to log the actual score we add
an optional return path — see §4.1. If we don't want to refactor that
signature now, log `"detected"` without a score.

### 3.4 EVA migration

`src/modes/eva/main.py` swaps its import:
```python
from src.core.log_format import configure_logging
# ...
configure_logging(
    event_tags=EVA_EVENT_TAGS,
    event_colors=EVA_EVENT_COLORS,
    level_env_var="EVA_LOG_LEVEL",
)
```

`EVA_EVENT_TAGS` and `EVA_EVENT_COLORS` mirror the constants currently in
`src/modes/eva/log_format.py`. EVA's existing `extra={"event": ...}` emit
calls in `session.py` and `websocket_handler.py` are untouched.

### 3.5 Files deleted

- `src/modes/eva/log_format.py` — superseded by `src/core/log_format.py`.
- `src/modes/pr/log_helpers.py` — superseded by `logging`.

### 3.6 Tests

- Rename `tests/test_eva_log_format.py` → `tests/test_log_format.py`;
  parameterize across the two tag dicts so both modes' formatters are
  covered by one fixture.
- Add a PR-specific test asserting `[WAKE]` and `[TTS]` records are rendered
  with their respective colors.

## 4. Wake-word re-fire fix

### 4.1 WakeWordDetector.reset()

Add to `src/voice/wake_word.py`:

```python
def reset(self) -> None:
    """Clear openWakeWord's internal melspec/embedding buffers."""
    self._model.reset()
```

openWakeWord 0.6.x's `Model` exposes `reset()`. If runtime check shows it
doesn't, the fallback is to re-instantiate `Model(...)` with the cached
paths — correct but slower (~100 ms reload). The implementation step will
confirm.

Optional: `process()` returns the max score it saw alongside the bool so the
`[WAKE]` log line can render the score. This is a small breaking change to
the callable; we'll add a `process_with_score() -> tuple[bool, float]`
sibling instead to keep `process()` stable.

### 4.2 Three-state audio mux in `voice_loop`

`src/modes/pr/main.py` extends the existing `state` flag to three values:

```python
state = {"mode": "wake"}        # 'wake' | 'capture' | 'playback'
wake_cooldown_until = 0.0       # monotonic deadline; 0 = no cooldown active

def callback(indata, frames, time_info, status):
    if state["mode"] == "playback":
        return                   # drop chunk; mic deaf during TTS
    chunk = ...
    if state["mode"] == "wake":
        if time.monotonic() < wake_cooldown_until:
            return               # post-playback cooldown
        triggered, score = wake.process_with_score(chunk)
        if triggered:
            main_loop.call_soon_threadsafe(wake_triggered.set)
            ...stash score for the [WAKE] log line...
    else:                         # capture
        main_loop.call_soon_threadsafe(capture_queue.put_nowait, chunk)
```

### 4.3 Loop-level transitions

```python
WAKE_COOLDOWN_S = 0.3   # module scope; tunable

# After classification + response_text computed:
state["mode"] = "playback"
log.info("speaking %.1fs", playback_duration_s, extra={"event": "tts"})
await main_loop.run_in_executor(None, lambda: play_blocking(audio_out, tts.sample_rate))

# Playback done:
wake.reset()
wake_cooldown_until = time.monotonic() + WAKE_COOLDOWN_S
state["mode"] = "wake"
```

### 4.4 Why all three mitigations at once

The user reported the re-fire timing varies. Each mitigation addresses one
suspect cause:

| Cause | Mitigation |
|---|---|
| Mic picks up Piper's own audio | `state="playback"` drops mic chunks |
| Stale wake-word activation from user's own utterance | `wake.reset()` on playback→wake |
| Echo tail or hardware buffer lag after Piper stops | 300 ms cooldown |

Cost: 300 ms latency before the next "hey corvus" can fire after a reply.
Negligible given the conversational cadence.

### 4.5 Tests

- Unit: mock `wake.process_with_score` to verify the callback drops chunks
  in `playback` and during cooldown.
- Unit: `WakeWordDetector.reset()` is callable (smoke).
- Manual acceptance: speak 10 single utterances; wake-word should fire
  exactly once per utterance.

## 5. PR mode sees EVA data

### 5.1 Mask change in MultilabelClassifier

`src/core/classifier/multilabel_classifier.py` — when `mode == "pr"`, load
both catalogs and union their intent lists:

```python
if mode == "pr":
    catalog_paths = [
        catalogs_dir / "intentPR.json",
        catalogs_dir / "intenteva.json",
    ]
else:  # "eva" — unchanged
    catalog_paths = [catalogs_dir / "intenteva.json"]

active_labels: set[str] = set()
for path in catalog_paths:
    active_labels.update(row["intent"] for row in json.loads(path.read_text()))
```

EVA mask stays at 45 labels. PR mask grows from 43 to 88. The boot log line
records the active count so any mis-wiring is visible at startup.

### 5.2 EVA field-path table for the PR registry

Add to `src/core/responder/registry_pr.py`:

```python
_EVA_FIELD_PATHS: dict[str, str] = {
    # Symmetric eva1/eva2 reads — pattern: get_<field>_eva{N} → telemetry.eva{N}.<field>
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
    # Asymmetric labels (PR-Model trained but irregular):
    "get_battery_level_eva2":            "telemetry.eva2.battery_level",
    "get_primary_battery_level_eva1":    "telemetry.eva1.primary_battery_level",
    "get_secondary_battery_level_eva1":  "telemetry.eva1.secondary_battery_level",
}
# 45 entries total.
```

### 5.3 Build merged registry

```python
REGISTRY_PR_FULL: dict[str, ResponseFn] = {
    **REGISTRY_PR,  # 43 entries — unchanged
    **{label: template_handler(label, "eva", path)
       for label, path in _EVA_FIELD_PATHS.items()},  # 45 entries
}
assert len(REGISTRY_PR_FULL) == 88
```

### 5.4 Wire into PR main

`src/modes/pr/main.py` imports `REGISTRY_PR_FULL` instead of `REGISTRY_PR`
and passes it into both `voice_loop` and `text_loop` for `dispatch.respond`.

### 5.5 Units and decimal places

Both constraints are satisfied transparently by the existing infrastructure:

- `src/core/responder/template_handler.py::_format_value` already renders
  `float` values as `f"{value:.2f}"`.
- All 45 EVA-side templates in `INTENT_RESPONSE_TEMPLATES` already spell out
  units for Piper readability (`P S I`, `R P M`, `percent`, `degrees
  Celsius`, `beats per minute`).

Verified: every label in `_EVA_FIELD_PATHS` has a matching key in
`INTENT_RESPONSE_TEMPLATES`. No new templates need to be authored.

### 5.6 Risk surface

The leaf names in `_EVA_FIELD_PATHS` assume TTTDTT's EVA telemetry payload
uses `eva1.<snake_case>` and `eva2.<snake_case>` keys. When the cache lookup
fails (missing key or stale channel), `template_handler` returns
`TELEMETRY_UNAVAILABLE_REPLY` — a clean fallback that Piper speaks as
"Telemetry unavailable right now." A wrong leaf name therefore surfaces as
a clear runtime symptom rather than a crash. Live-payload verification is a
follow-up task; see §7.

### 5.7 Tests

- `tests/test_registry_pr.py`: add an assertion that the merged registry has
  88 entries; spot-check a handful of EVA labels resolve to handlers that
  read the `eva` channel (mock the cache, assert the formatted response).
- `tests/test_multilabel_classifier.py`: in `mode="pr"`, the mask sum is 88
  and `argmax` can return an EVA label given an EVA-shaped logit vector.
- `tests/test_phase2_smoke.py`: extend with an end-to-end PR-mode case that
  populates an `eva` cache snapshot and dispatches "what is EVA 1's heart
  rate" through to a Piper-ready string.

## 6. File-level change summary

| File | Action |
|---|---|
| `src/core/log_format.py` | NEW — parameterized formatter |
| `src/modes/eva/log_format.py` | DELETE — content moved to `src/core/log_format.py` |
| `src/modes/eva/main.py` | EDIT — import and call shared `configure_logging` |
| `src/modes/pr/main.py` | EDIT — adopt `logging`; three-state audio mux; wake cooldown; use `REGISTRY_PR_FULL` |
| `src/modes/pr/log_helpers.py` | DELETE |
| `src/voice/wake_word.py` | EDIT — `reset()`, optional `process_with_score()` |
| `src/core/classifier/multilabel_classifier.py` | EDIT — PR mask = union of both catalogs |
| `src/core/responder/registry_pr.py` | EDIT — add `_EVA_FIELD_PATHS`, build `REGISTRY_PR_FULL` |
| `tests/test_log_format.py` | RENAMED from `test_eva_log_format.py` + parameterized |
| `tests/test_registry_pr.py` | EDIT — assert 88 entries + spot-checks |
| `tests/test_multilabel_classifier.py` | EDIT — PR mask = 88 |
| `tests/test_phase2_smoke.py` | EDIT — add EVA-from-PR end-to-end |
| `tests/test_voice_wake_word.py` | NEW or EDIT — smoke `reset()` |

## 7. Rollout

Three independent landings, each behavior-isolated:

1. **Logging port** — pure refactor, behavior-preserving. Test by running
   both `corvus-eva` and `corvus-pr` and comparing console output to the
   pre-change baseline.
2. **PR sees EVA data** — additive. Existing PR rover queries keep working
   (their handlers and labels are untouched). New EVA queries either return
   correctly-formatted strings or `TELEMETRY_UNAVAILABLE_REPLY` if the leaf
   name needs adjusting against the live TTTDTT payload.
3. **Wake-word re-fire fix** — isolated to PR voice loop. `--text` mode is
   not affected. Manual acceptance: 10 utterances, 10 fires.

Follow-up after merge: in a live session, sanity-check each EVA leaf name
against the actual TTTDTT EVA payload. Any mismatches show as
`TELEMETRY_UNAVAILABLE_REPLY` and can be fixed in a one-line PR per leaf.

## 8. Out of scope

- Retraining the multilabel classifier — the checkpoint already covers all
  88 labels.
- Changes to EVA mode dispatch, registries, or Unity contract.
- Adding any of the EVA-side `set_*` / menu / procedure / task verbal-acks
  to PR — those are not in `intenteva.json` and not in the multilabel label
  set, so they remain EVA-only.
- TTS write paths for the PR `set_*` intents — still verbal-ack only, same
  as today.
