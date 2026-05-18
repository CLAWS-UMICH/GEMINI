# GEMINI STT Transport-Layer Port — Merge Notes

> Companion doc for `GEMINI_TRANSPORT_PORT_PLAN.md` and `GEMINI_TRANSPORT_PORT_AUDIT.md`. Use this when rebasing/merging branch `stt-offload-port-plan` into `main` to anticipate conflict hotspots.

**Branch:** `stt-offload-port-plan` → `main`
**Baseline commit on main:** `ee599ff`
**Commits on this branch:** 12 (see `git log ee599ff..stt-offload-port-plan`)

---

## TL;DR for someone resolving conflicts

- **Transport swap:** Unity stopped doing on-device Whisper STT. Audio now streams as binary PCM to a Python EVA server; Python returns a JSON `{"type":"final", ...}` frame with the spoken response baked in.
- **API preserved:** `IntentResponse`, `IntentParameters`, `CorvusLatency` classes and the three events (`OnWakeDetected`, `OnIntentReceived`, `OnIntentResponseReceived`) keep their original shapes — anything subscribing to them keeps working.
- **`CorvusARBridge.Dispatch` switch is unchanged** — but the wrapper that calls it (`OnIntentResponseReceived`) now prefers Python's `response` string for the spoken/displayed text.
- **Two files re-serialized by Unity** (`GEMINI.unity`, `Corvus.prefab`) — large diffs that are mostly noise; semantic changes are limited and described below.
- **whisper.unity package removed.** Don't be alarmed by `Library/PackageCache/com.whisper.unity*` disappearing.

---

## Files changed — conflict risk table

| File | Risk | What changed | If main also touches it |
|---|---|---|---|
| `Assets/CLAWS/Backend/Networking/CorvusController.cs` | **HIGH** | Heavy rewrite. New state machine, new DTOs (StartMessage/StopMessage/FrameEnvelope/FinalFrame), `_audioStreamer` SerializeField added, `_whisper`/`_microphoneRecord` SerializeFields removed, `CommandRequest` class removed. | Read both versions side by side. Our version is the source of truth for the new wire protocol. |
| `Assets/CLAWS/Backend/Networking/CorvusARBridge.cs` | **MEDIUM** | One small edit at line 87-93 of `OnIntentResponseReceived`: prefers `raw.response` over `Dispatch(...)`'s return when Python provides a non-empty response. **The 611-line `Dispatch` switch itself is unchanged.** Original plan listed this file as untouchable; the constraint was lifted post-smoke-test. |
| `Assets/CLAWS/Backend/Networking/WebSocketClient.cs` | LOW | Added `SendBinaryAsync(byte[])` method, between `SendAsync(string)` and `ReceiveAsync()`. Strict addition. |
| `Assets/CLAWS/Backend/Networking/AudioStreamer.cs` | **NEW FILE** | MonoBehaviour: Unity `Microphone` → `WebSocketClient.SendBinaryAsync` at 100ms cadence. |
| `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs` | **NEW FILE** | Pure static helper: `FloatsToInt16(float[]) → byte[]` little-endian, plus `ChunkSamples` helper. |
| `Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef` | **NEW FILE** | New isolated production asmdef for pure-C# audio code. `autoReferenced: true`. |
| `Assets/CLAWS/Testing/CorvusTest.cs` | LOW | `SendVoicePhraseAsync` (async, called `SendCommandAsync`) replaced with sync `SendVoicePhrase` that always exercises `SimulateIntent` locally. `_simulateWhenDisconnected` SerializeField removed. |
| `Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab` | **HIGH** | YAML surgery: removed `WhisperManager` + `MicrophoneRecord` MonoBehaviour blocks, added `AudioStreamer` block (fileID `7400000000000000001`, GUID `bba46168865945e783a71159c09084c2`). CorvusController's `_whisper`/`_microphoneRecord` lines replaced with `_audioStreamer`/`_streamingTimeoutSec`. Unity also re-serialized other parts of the prefab on first open after the migration — much of the diff is positional noise. |
| `Assets/CLAWS/GEMINI.unity` | **HIGH** | Converted scene's standalone CorvusController GameObject into a `Corvus.prefab` PrefabInstance. The scene's old standalone `CorvusARBridge` + `DialogueManager` are kept (they have scene-level wiring like `ScreenManager`/`Pathfinding`); the prefab's duplicate `DialogueManager` + `CorvusARBridge` children are disabled via `m_IsActive=0` override. Stale `ws://172.20.10.3:8765` removed (prefab default is `ws://localhost:8765`). |
| `Assets/CLAWS/Phase-1/Features/Navigation.unity` | UNCHANGED | Was already a prefab instance (`m_CorrespondingSourceObject` set) — no edit needed; prefab changes propagate automatically. |
| `Packages/manifest.json` | LOW | Removed `"com.whisper.unity"` line. JSON parses; trailing commas correct. |
| `Packages/packages-lock.json` | LOW | Unity regenerated — whisper.unity entry gone. Auto-managed; don't hand-edit. |
| `Assets/StreamingAssets/Whisper/` | **DELETED** | `ggml-tiny.en.bin` (77 MB) + meta + folder meta all removed. |

### Hard constraints honored (untouched)

These files have **zero diff** vs `main`:
- `Assets/CLAWS/Phase-1/Features/AIA/Scripts/CorvusHalo.cs`
- `Assets/CLAWS/UI/IntentDisplayUI.cs`
- `Assets/CLAWS/Backend/Networking/CorvusTTS.cs`

If `main` modifies any of these, the merge resolves cleanly — keep their version. We never touched them by design (events on `CorvusController` are signature-stable).

---

## Hotspot guidance

### `CorvusController.cs` — heavy rewrite

The class kept the same name, namespace (`CLAWS.Networking`), public events, and public `TriggerWakeDetected()` method. Everything else inside is new:

- **State machine:** `enum State { IDLE, WAKE, STREAMING, SPEAKING }`. Mostly internal.
- **DTOs added:** `StartMessage`, `StopMessage`, `FrameEnvelope`, `FinalFrame`. Sit between `IntentResponse` and `CorvusLatency` in the same file.
- **DTO removed:** `CommandRequest` (was used by the old text-command protocol — Python now drives via streaming).
- **Inspector fields:** old (`_whisper`, `_microphoneRecord`) gone; new (`_audioStreamer`, `_streamingTimeoutSec`) added.
- **Threading caveat (known follow-up):** `HandleFinalFrame` writes `_state` from the WebSocket listener thread while also enqueuing main-thread work. Reviewer flagged race potential. Not blocking; left as-is per plan.

If main edited this file: take our version wholesale; reapply main's changes on top if they're additive (new event subscribers, new logging, etc.).

### `CorvusARBridge.cs` — surgical edit

The plan originally listed this as untouchable. After Task 9 smoke test we lifted that and added a 2-line fix at `OnIntentResponseReceived`:

```csharp
// Was:
spoken = Dispatch(raw.intent, p, raw.response);

// Now:
var localSpoken = Dispatch(raw.intent, p, raw.response);
spoken = !string.IsNullOrEmpty(raw.response) ? raw.response : localSpoken;
```

The entire `Dispatch(...)` switch body and helpers (`ReadVital`, `OpenScreen`, etc.) are byte-identical to main. If main also touches `OnIntentResponseReceived`, merge carefully — our change runs Dispatch first (preserves side effects), then overrides the *spoken* string only.

### `Corvus.prefab` and `GEMINI.unity` — Unity YAML

Both files had Unity re-serialize parts of them after the migration. Large diff lines are mostly:

- Block re-ordering (e.g., AudioStreamer block moved inline).
- Inspector defaults filling in (e.g., `CorvusTest._corvusARBridge`, `_navTargetName`, etc. — they had Inspector defaults that hadn't been written before).
- New `m_IsActive: 0` overrides on the prefab instance in the scene (intentional — disabling duplicate children).

**Semantic changes only:**
- `Corvus.prefab`: AudioStreamer component added, Whisper components removed, CorvusController's serialized field set changed.
- `GEMINI.unity`: standalone CorvusController GameObject removed; PrefabInstance for `Corvus.prefab` added; `CorvusARBridge._corvusController` and `_tts` re-pointed at stripped refs in the prefab instance.

If main also edited these files, do conflict resolution **in Unity Editor**, not in YAML. Open the conflicted scene/prefab, accept "Use mine" for the bulk of changes, then re-do main's specific edits (move objects, add components, etc.) in the Inspector. Hand-editing the YAML is fragile.

---

## WebSocket wire contract (for anyone touching the protocol)

**Unity → Python (binary or text):**

- `{"type":"start","sample_rate":16000,"channels":1}` — sent at wake.
- Binary frames: little-endian int16 PCM, ~100 ms chunks (1600 samples at 16 kHz).
- `{"type":"stop"}` — sent on timeout (5 s default) or shutdown.

**Python → Unity (text):**

- `{"type":"final","response":"...","transcript":"...","intent":"...","confidence":0.95,"latency_ms":234.5}`
  - `response` is the user-facing string Unity speaks/displays. Make it non-empty for vitals/data intents.
  - `intent` maps to a `case` in `CorvusARBridge.Dispatch`. Empty → coerced to `"unhandled"`.
  - `parameters` is currently omitted (Phase 1 NN classifier doesn't extract slots); Unity sets `IntentResponse.parameters = null`, Dispatch uses null-safe `p?.SLOT` access.
- `{"type":"partial",...}` — reserved by the contract, currently ignored by Unity.
- Any other `type` value → logged as warning, dropped.

Malformed JSON or missing `type` → logged as warning, dropped.

---

## Inspector wiring (won't show in code diff)

These are scene-side wirings worth verifying after a merge with conflicts in `GEMINI.unity`:

- `Corvus` prefab instance — single GameObject expanded to 4 children: `Corvus/CorvusController` (active), `Corvus/DialogueManager` (disabled via override), `Corvus/CorvusARBridge` (disabled via override).
- Scene's standalone `CorvusARBridge`:
  - `_corvusController` → stripped ref into prefab instance's CorvusController component.
  - `_tts` → stripped ref into prefab instance's CorvusTTS component.
  - All other slots (`_screenManager`, `_pathfinding`, `_uiaController`, `_navigationController`, `_taskDetailScreen`, `_playerTransform`, `_dialogueManager`) wired to scene-level objects unchanged.
- The new `Corvus/CorvusController` GameObject has an `AudioStreamer` component on it; CorvusController's `_audioStreamer` field is wired internally by the prefab.

If you see a `Missing (Mono Script)` warning in the Console after merge, it's almost always a stale Whisper component reference in a non-prefab scene that wasn't touched. The plan accepted this as "harmless residue."

---

## Tests

12 NUnit tests committed under `Assets/CLAWS/Tests/Editor/`:
- 1 smoke test (`SmokeTest_TestRunnerExecutes_Passes`)
- 7 `FloatsToInt16` tests (boundaries, clamping, empty input, mid-value rounding)
- 4 `ChunkSamples` tests (exact multiple, partial tail, smaller-than-chunk, data preservation)

Run via `Window → General → Test Runner → EditMode → Run All`. Expected: 12 green.

Two new asmdefs gate the test scope: `CLAWS.Audio.asmdef` (production, auto-referenced) and `CLAWS.Audio.Tests.Editor.asmdef` (editor-only, references NUnit + CLAWS.Audio).

---

## Known follow-ups (non-blocking)

1. **`CorvusController.HandleFinalFrame` threading** — `_state` writes happen on the WebSocket listener thread alongside main-thread enqueues. Possible race producing stale event delivery after timeout. Fix sketch: move all `_state` writes inside `UnityMainThreadDispatcher.Enqueue`; add a generation counter to the timeout watchdog.
2. **`_corvusTTS` and `_lmcc` SerializeFields on CorvusController** — `_corvusTTS` is dead code (never read). `_lmcc` is live but unwired in the prefab; logging is null-safe-skipped. Wire `_lmcc` when an LMCC server is available.
3. **TSSConnection / live vitals data on Unity side** — the `CorvusARBridge.ReadVital(...)` path reads Unity's local TSSConnection cache, which may be 0 if TSSConnection is not connected. Python now provides the formatted vital string via `response`, so this isn't user-visible — but the `Check(...)` warning generators in `BuildWarningsSpoken` still use the local cache. Wire `TSSConnection` correctly if those warnings matter.
4. **`Navigation.unity` smoke test deferred** — only `GEMINI.unity` was driven through end-to-end. `Navigation.unity` is already a prefab instance so it should pick up changes automatically, but it hasn't been verified in Play mode.
