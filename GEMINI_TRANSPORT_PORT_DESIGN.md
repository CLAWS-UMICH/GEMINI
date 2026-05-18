# GEMINI Transport-Layer Port — Design Spec

**Date:** 2026-05-17
**Repo:** `git@github.com:CLAWS-UMICH/GEMINI.git`
**Baseline:** `ee599ff` (`main`, "Changes to the Corvus TTS")
**Sister repo (read-only reference):** `/mnt/c/Users/sunaa/Documents/CLAWS/CORVUS_Integration` branch `AI-integration-ar-merge` — already has the new transport layer working.

---

## 1. Problem

GEMINI's Unity client and the new Python EVA server (`AI-new-corvus-server` branch in `CORVUS_PythonServer`) do not share a protocol.

| Layer | GEMINI (current) | Python EVA server (new) |
|---|---|---|
| Wake → STT | Whisper on Unity (intended path; **actually unwired** today — see §3) | Whisper on Python (faster-whisper, base.en) |
| Up wire | Text JSON `{"command":"<transcript>"}` after local Whisper | Text JSON `{"type":"start", sample_rate, channels}` + raw binary PCM (int16 LE, 16 kHz, mono) |
| End-of-speech | Whisper.unity's VAD (effectively unused — controller relies on `OnRecordStop`) | Silero VAD on Python with 700 ms hangover |
| Down wire | Rich `IntentResponse` (status, intent, confidence, matched_keywords, request_id, latency_ms, timestamp, response, parameters) | Compact `{"type":"final", response, transcript, intent?, confidence?, latency_ms?}` (no `parameters` today, no `partial` frames) |

Tomorrow GEMINI will be run live against the EVA server. Without a port, the WebSocket handshake succeeds but no audio reaches Python and no `final` frame is understood.

## 2. Goal

Replace **only** the transport layer in GEMINI so the existing intent-routing logic (`CorvusARBridge.Dispatch`, 611 lines) keeps working unchanged against the new Python server.

## 3. Non-goals

- Touching any of the 590 lines of intent routing in `CorvusARBridge.cs`. The switch already covers all 87 EVA-server labels.
- Touching `IntentDisplayUI`, `CorvusHalo`, `CorvusTTS`, `DialogueManager`, `ScreenManager`, `Pathfinding`, `TaskDetailScreen`, `UIAController`, `NavigationController`, `EventBus`, AR/vitals subsystems.
- Fixing the wake-word-after-idle reliability bug. Deferred.
- Adding intent-routed parameterized actions that Python doesn't supply slots for (`Set_navigation_target`, `Add_waypoint`, etc.) — Python omits `parameters` today; the Dispatch handles `null` slots gracefully.
- Implementing a live-transcript overlay (`partial` frames are not emitted by Python).

## 4. Audit findings worth knowing before touching code

These shaped the design and must be carried into the implementation plan.

1. **GEMINI's Whisper path is already dead.** In `Corvus.prefab` the `CorvusController._whisper` and `_microphoneRecord` fields are wired to `fileID: 0` (None). The components physically exist on the prefab GameObject but `CorvusController.Start` guards on `_microphoneRecord != null` and skips initialization. **Effective consequence:** no live voice path runs in GEMINI today — only `CorvusTest.cs` keyboard shortcuts exercise `Dispatch` via `SendCommandAsync(phrase)`.
2. **Three events on `CorvusController` have subscribers** (all must be preserved):
   - `OnWakeDetected()` — subscribed by `CorvusHalo`.
   - `OnIntentReceived(string intent, float confidence, string response, CorvusLatency latency)` — subscribed by `CorvusHalo` and `IntentDisplayUI`.
   - `OnIntentResponseReceived(IntentResponse, CorvusLatency)` — subscribed by `CorvusARBridge`.
3. **`CorvusTest.cs` calls `SendCommandAsync(phrase)`.** That method goes away when the text protocol is removed. The harness must be repointed.
4. **`Corvus.prefab` is the source of truth.** It is instanced in `GEMINI.unity` and `Phase-1/Features/Navigation.unity`. **Edit the prefab, not the scenes**, so both scenes inherit the changes.
5. **Default WS URL in source** is `ws://172.20.10.3:8765` (Maca's test host). Local Python server is `ws://localhost:8765`. Per-scene inspector override exists.
6. **Python's `parameters` is always omitted** in Phase 1. The receiver should map missing-or-null → `IntentResponse.parameters = null` and Dispatch's null-safe slot reads (`p?.NAVIGATION_TARGET_NAME`) handle this. Parameterized intents will fire with null slots and degrade verbally — out of scope to fix here.
7. **Python emits `intent: "unhandled"`** when confidence < 0.65. `Dispatch`'s `default:` branch will speak `IntentResponse.response` ("I'm not sure I caught that — could you say it again?") via the existing fallback path — no special handling needed.
8. **Python's intent vocabulary is 87 labels** covering all of GEMINI's `Dispatch` cases (vitals_*, open_menu_*, start_procedure_*, get_*, navigation, tasks, waypoints, sets). No mismatch.

## 5. Architecture

```
HoloLens (Unity / GEMINI)                    Localhost (Python EVA server)
────────────────────────────────────────────────────────────────────
KeywordRecognizer ──"hey corvus"──┐
                                  │
                          CorvusController (state machine)
                                  │
              ┌───────────┬───────┴───────┬───────────┐
              ▼           ▼               ▼           ▼
          AudioStreamer  WebSocketClient  CorvusTTS  Wake/Halo events
          (mic→PCM)      (.SendBinaryAsync)
                          │
                          │ binary PCM (1600 samples / 100 ms)
                          ▼
                  ──── ws://localhost:8765 ────
                          │
                          ▼
                  Silero VAD → faster-whisper → NN classifier → REGISTRY_EVA
                          │
                          ▼ JSON {"type":"final","response":...,"intent":...}
                          │
                          ▲
   ┌──────────────────────┘
   ▼
CorvusController.HandleMessageReceived
   │
   ▼
Build IntentResponse from FinalFrame fields
   │
   ▼
Fire OnIntentReceived + OnIntentResponseReceived (existing events, unchanged)
   │
   ▼
CorvusARBridge.Dispatch ── unchanged 611-line switch ── Unity APIs
   │
   ▼
DisplayResponse + CorvusTTS.Speak
```

## 6. Unity state machine

Identical to the one already shipped in `CORVUS_Integration`:

```
[IDLE] ──"hey corvus"──► [WAKE] ──send {"type":"start"}─► [STREAMING] ──PCM chunks every ~100ms──►
   ▲                                                          │
   │                                              receive {"type":"final"}
   │                                                          ▼
   └─────────────────────────────────────────── [SPEAKING] ◄── close mic
                                                    │
                                                    │ Dispatch → TTS done
                                                    └──── back to IDLE
```

**Timeout:** if `STREAMING` lasts longer than `_streamingTimeoutSec` (default 5 s) without `final`, Unity sends `{"type":"stop"}`, closes the mic, returns to IDLE.

## 7. Wire-format contract Unity must honor

This is the same v1 contract documented in the sister repo at `CORVUS_Integration/UNITY_PYTHON_CONTRACT.md` and confirmed by the Python team in `corvus-eva` README:

### Unity → Python
- Text `{"type":"start","sample_rate":16000,"channels":1}` — required, exact ints.
- Binary frames: int16 little-endian PCM, mono, 16 kHz, any chunk size (we send 1600 samples = 3200 bytes per chunk).
- Text `{"type":"stop"}` — optional; sent only on Unity timeout.

### Python → Unity
- Text `{"type":"final", "response": "...", "transcript"?, "intent"?, "confidence"?, "parameters"?, "latency_ms"?}` exactly once per utterance.
- `parameters` always omitted in Phase 1. `intent` may be the literal string `"unhandled"`.
- No `partial` frames.

## 8. Preservation contract (the non-negotiables)

These are the surfaces that downstream code depends on. **Implementer must preserve them exactly.**

1. Event `OnWakeDetected()` — fires on wake-word phrase match before any streaming begins.
2. Event `OnIntentReceived(string intent, float confidence, string response, CorvusLatency latency)` — fires once per final, on the Unity main thread.
3. Event `OnIntentResponseReceived(IntentResponse intentResponse, CorvusLatency latency)` — fires once per final, on the Unity main thread. The `IntentResponse` object must have these populated:
   - `intent` ← `FinalFrame.intent` (or `"unhandled"` if absent)
   - `confidence` ← `FinalFrame.confidence` (or 0 if absent)
   - `response` ← `FinalFrame.response` (always present from Python)
   - `parameters` ← `null` (Python omits these in Phase 1)
   - `latency_ms` ← `FinalFrame.latency_ms` (or 0 if absent)
   - `transcript`, `status`, `matched_keywords`, `request_id`, `timestamp` — leave at default (`Dispatch` does not read these)
4. Class `IntentResponse` and `IntentParameters` — unchanged shape and namespace.
5. Class `CorvusLatency` — unchanged fields. `STT` becomes 0 (Unity no longer transcribes); `classification` is repurposed as server-side processing time from `FinalFrame.latency_ms`; `network`, `roundTrip`, `TTS`, `total` continue to be measured as before.
6. `CorvusARBridge.cs`, `CorvusHalo.cs`, `IntentDisplayUI.cs`, `CorvusTTS.cs` — **zero edits.**
7. `Dialogue`, `DialogueManager`, all AR subsystems referenced by `Dispatch` — zero edits.

## 9. Files to add, modify, delete

### Add
| Path | Source | Purpose |
|---|---|---|
| `Assets/CLAWS/Backend/Networking/Audio/CLAWS.Audio.asmdef` (+ meta) | Copy from `CORVUS_Integration/Assets/CLAWS/Backend/Networking/Audio/` | Isolated assembly for pure-C# audio helpers |
| `Assets/CLAWS/Backend/Networking/Audio/PcmConverter.cs` (+ meta) | Same | float→int16 LE conversion, chunk splitter |
| `Assets/CLAWS/Backend/Networking/AudioStreamer.cs` (+ meta) | Same | `MonoBehaviour` that drives `Microphone` → `WebSocketClient.SendBinaryAsync` |
| `Assets/CLAWS/Tests/Editor/CLAWS.Audio.Tests.Editor.asmdef` (+ meta) | Copy from `CORVUS_Integration/Assets/CLAWS/Tests/Editor/` | Edit-mode test assembly |
| `Assets/CLAWS/Tests/Editor/PcmConverterTests.cs` (+ meta) | Same | 11 NUnit tests for `PcmConverter` |
| `Assets/CLAWS/Tests/Editor/SmokeTest.cs` (+ meta) | Same | Proves test runner is alive |

### Modify
| Path | Change |
|---|---|
| `Assets/CLAWS/Backend/Networking/WebSocketClient.cs` | Add `SendBinaryAsync(byte[] data)` (uses `WebSocketMessageType.Binary`). No success-path `Debug.Log` (PCM frames at 10 Hz would spam). |
| `Assets/CLAWS/Backend/Networking/CorvusController.cs` | Replace transport layer (see §10). Preserve `IntentResponse`, `IntentParameters`, `CorvusLatency`, all three events, `_wakeWords`, `KeywordRecognizer`, `CorvusTTS`/`_lmcc` wiring. |
| `Assets/CLAWS/Testing/CorvusTest.cs` | Replace `_corvusController.SendCommandAsync(phrase)` call with the existing `SimulateIntent` fallback path; remove `_simulateWhenDisconnected` flag (it becomes the only path). The keyboard harness becomes a pure local Dispatch exerciser. |
| `Assets/CLAWS/Phase-1/Features/AIA/Corvus.prefab` | YAML edit: remove the orphan `WhisperManager` and `MicrophoneRecord` MonoBehaviour blocks and their entries in the prefab GameObject's `m_Component` list. Add a new `AudioStreamer` MonoBehaviour block. Wire `_audioStreamer` on `CorvusController` to the new block. Remove now-orphan `_whisper`/`_microphoneRecord` serialized field lines on `CorvusController` (already at `fileID: 0` so they're orphan placeholders). |
| `Packages/manifest.json` | Remove the `com.whisper.unity` line. |

### Delete
| Path | Reason |
|---|---|
| `Assets/StreamingAssets/Whisper/ggml-tiny.en.bin` (+ meta) | ~77 MB model no longer loaded |
| `Assets/StreamingAssets/Whisper/` directory + its meta | Empty after model removal |
| `Library/PackageCache/com.whisper.unity@*` | Auto-cleaned by Unity on reimport |

### Auto-regenerated by Unity (commit after reimport)
- `Packages/packages-lock.json` — Unity will rewrite without the whisper.unity entry.

## 10. CorvusController rewrite — explicit shape

Drop existing `using Whisper;` and `using Whisper.Utils;`. Add `using System.Collections;` (for `IEnumerator`).

Add new private DTOs alongside the existing ones (`IntentResponse`, `IntentParameters`, `CorvusLatency`):

```csharp
[System.Serializable] public class StartMessage   { public string type = "start"; public int sample_rate = 16000; public int channels = 1; }
[System.Serializable] public class StopMessage    { public string type = "stop"; }
[System.Serializable] public class FrameEnvelope  { public string type; }
[System.Serializable] public class FinalFrame {
    public string type;
    public string response;
    public string transcript;
    public string intent;
    public float  confidence;
    public float  latency_ms;
}
```

(`CommandRequest` is removed.)

Class body becomes a state machine — see the working reference at `CORVUS_Integration/Assets/CLAWS/Backend/Networking/CorvusController.cs` (commit `7693180`). The only difference for GEMINI is the event-firing block in `HandleFinalFrame`:

```csharp
// In HandleFinalFrame, after building CorvusLatency:
var ir = new IntentResponse {
    intent     = string.IsNullOrEmpty(finalFrame.intent) ? "unhandled" : finalFrame.intent,
    confidence = finalFrame.confidence,
    response   = finalFrame.response ?? "",
    parameters = null,                      // Python omits in Phase 1
    latency_ms = finalFrame.latency_ms,
    // status / matched_keywords / request_id / timestamp / transcript:
    // leave at their zero-value defaults; Dispatch does not read them.
};

UnityMainThreadDispatcher.Instance().Enqueue(() => {
    OnIntentReceived?.Invoke(ir.intent, ir.confidence, ir.response, latency);
    OnIntentResponseReceived?.Invoke(ir, latency);
});

LogToLMCC(finalFrame.transcript, ir.intent, ir.confidence);
```

This is the only place GEMINI diverges from the sister-repo reference implementation, and it's the seam that keeps `Dispatch` working unchanged.

## 11. Test harness change

`CorvusTest.cs` currently does:
```csharp
if (_corvusController.IsConnected)
{
    await _corvusController.SendCommandAsync(phrase);   // <-- removed method
    return;
}
// else: SimulateFallback via _corvusARBridge.SimulateIntent(...)
```

After the port, `SendCommandAsync` does not exist (no text path on the wire). Make the keyboard shortcuts always run `SimulateIntent`, which is the existing local-only path that exercises `Dispatch` without Python. Remove `_simulateWhenDisconnected` (always-on now). Voice testing via the wake word is the live path.

## 12. Error handling

| Failure | Behavior |
|---|---|
| WebSocket disconnect mid-stream | Stop mic via `AudioStreamer.StopStreaming`, return to IDLE, log error. Next wake retries connection. |
| Python returns `final` with empty `response` | TTS speaks nothing; halo still hits `foundAnswer`/idle so the animation completes; Dispatch still runs (intent likely `"unhandled"`). |
| 5 s timeout in STREAMING | Send `{"type":"stop"}`, close mic, return to IDLE. No spoken fallback. |
| Microphone permission denied / device missing | `AudioStreamer.StartStreaming` logs `[AudioStreamer] No microphone devices available`; state machine returns to IDLE. |
| Malformed JSON from Python | Log + drop frame. State machine unchanged. |
| Binary frame received from Python (not expected) | Log warning, drop. |

## 13. Testing strategy

**Pure C# (Edit-mode):**
- Port `PcmConverterTests.cs` (11 cases). Verifies `FloatsToInt16` clipping + LE byte order, `ChunkSamples` boundary cases.
- `SmokeTest.cs` verifies the test runner is alive (asserts `1+1==2`).
- Run via `Window > General > Test Runner > EditMode > Run All`. Expected: 12 passed.

**Manual integration:**
- Start Python EVA server (`corvus-eva` from `CORVUS_PythonServer` venv).
- Open `Assets/CLAWS/GEMINI.unity`, press Play.
- Console expectations: `WebSocket connected successfully!`, `CORVUS wake word listening: 'hey corvus'`.
- Say "hey corvus" + a phrase from any group in the Python intent vocab. Expect:
  - `Wake word detected: hey corvus`
  - `[AudioStreamer] Streaming started`
  - Python receives PCM, finalizes via VAD, returns `final`
  - Dispatch fires the matching Unity action (vitals readout, screen open, etc.)
  - Piper speaks the response, halo wake → answer → idle, dialogue text appears
  - `[AudioStreamer] Streaming stopped`
- Keyboard harness: with the scene running, press digits 1-9 — `SimulateIntent` should drive `Dispatch` without Python.

## 14. Risks

1. **Prefab YAML edit is the highest-risk change.** A fileID collision or malformed YAML block can corrupt the prefab. Mitigation: surgical edits anchored on unique surrounding lines; verify by reading the prefab back after each edit; the `AudioStreamer` block must use a fresh unique `fileID` and be referenced from the prefab GameObject's `m_Component` list and from `CorvusController._audioStreamer`.
2. **Unity meta-file generation.** `PcmConverter.cs`, `AudioStreamer.cs`, asmdef files, and test files all need `.meta` siblings. The CORVUS_Integration sister repo's metas use stable random GUIDs; copy them verbatim (no GUID collision risk because they don't exist in GEMINI yet). For new prefab content (the AudioStreamer component block), use a freshly generated GUID for the m_Script reference — but that's not needed because we're referencing the `AudioStreamer.cs.meta` GUID we just added.
3. **`OnIntentResponseReceived` fires on background continuation in the sister repo.** The GEMINI version must enqueue it on the main thread (`UnityMainThreadDispatcher`) because `Dispatch` touches `GameObject.SetActive`, `EventBus.Publish`, etc. — Unity APIs that require the main thread.
4. **`com.whisper.unity` removal cascades to other scenes.** GEMINI has `WhisperManager`/`MicrophoneRecord` components in `GEMINI.unity` (2 instances) and possibly elsewhere. Per scope, **only touch `Corvus.prefab`**; let scene-level orphan components become "Missing (Mono Script)" warnings — harmless residue. Cleaning them is out of scope (it's the same scope decision the sister repo made for non-CORVUS scenes).
5. **WS URL is `172.20.10.3` in source code default.** Change to `ws://localhost:8765` in `CorvusController.cs` so a fresh inspector value resolves to localhost. Existing prefab/scene values override; document this in the implementation plan.

## 15. Out of scope (recap)

- `CorvusARBridge.Dispatch` body and helper methods.
- Any AR subsystem (screens, vitals, navigation, tasks, UIA, halo).
- Adding `intent` / `confidence` UI display refinements beyond what GEMINI already does.
- Implementing `parameters` extraction (Python omits today; would require model upgrade on the Python side).
- Wake-word reliability after long idle.
- `partial`-frame live transcript overlay.
- Migration to Jetson hardware.
- Cleaning Whisper components out of non-`Corvus.prefab` scenes.

## 16. Related references

- `CORVUS_Integration/STT_OFFLOAD_DESIGN.md` — original design that birthed the transport layer being ported here.
- `CORVUS_Integration/UNITY_PYTHON_CONTRACT.md` — wire-format spec; same one Python implements.
- `CORVUS_Integration/Assets/CLAWS/Backend/Networking/{Audio/,AudioStreamer.cs,WebSocketClient.cs,CorvusController.cs}` — working reference implementation at commit `42a5c94` (or any later commit on `AI-integration-ar-merge`).
- Python team's status report dated 2026-05-17 documenting the EVA server contract (`corvus-eva` entry point).
