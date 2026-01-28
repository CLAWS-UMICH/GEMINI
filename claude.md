# CORVUS AI Assistant - Project Context

## Project Overview
CORVUS is an AI voice assistant for NASA's Project GEMINI EVA operations, running on HoloLens 2. Provides real-time intent classification, text-to-speech feedback, and AR display for astronaut commands during spacewalks. Integrates with LMCC (Local Mission Control Center) for telemetry data and mission coordination.

## Architecture

### Unified Pipeline (Working)
```
Wake Word ("hey corvus") → KeywordRecognizer
    ↓
Astronaut Voice → Whisper STT → transcript text
    ↓
CorvusController.SendCommandAsync(transcript)
    ↓
WebSocket → Python Server → AI Classifier (keyword-based, real model pending)
    ↓
{intent: "check_vitals", confidence: 0.92}
    ↓
GetResponseForIntent() builds response (hardcoded, telemetry pending)
    ↓
Piper TTS speaks response (~70ms)
    ↓
LogToLMCC() for mission coordination (optional, not wired yet)
```

### Component Communication
- **Unity ↔ Python AI**: WebSocket (ws://localhost:8765) - intent classification
- **Unity ↔ LMCC**: Socket.IO (SocketIOClient) - telemetry, mission data, logging
- **STT**: whisper.unity (local Whisper ONNX model)
- **TTS**: Piper.unity (local, ~70ms after warmup)
- **AI**: Transformer classifier model (Python server)

### System Diagram
```
[NASA TSS] ──→ [LMCC Server] ←── [PR Client]
                  ↕       ↕
               [EV1]    [EV2]
              HoloLens  HoloLens
                 ↕
          [Python AI Server]
           (ws://localhost:8765)
```

## System Requirements

### Unity
- Version: **Unity 6 (6000.2.7f2)**
- AI Framework: **Inference Engine 2.4.1** (formerly Sentis)
- Required Packages: TextMeshPro, Input System, com.unity.ai.inference
- Additional: Newtonsoft.Json (via NuGet), SocketIOClient, whisper.unity
- Player Settings: "Allow unsafe code" enabled, Active Input Handling set to "Both"

### Python
- Version: 3.13+
- Package Manager: **uv**
- Libraries: FastAPI, uvicorn, websockets, torch, transformers, onnxruntime

### Hardware
- Development: Windows PC with GPU
- Target: HoloLens 2
- Edge Compute: NVIDIA Jetson Orin Nano (recommended)

## Project Structure

```
CORVUS_Integration/                         # Unity project
├── Assets/
│   ├── CLAWS/
│   │   ├── Backend/
│   │   │   ├── Networking/
│   │   │   │   ├── CorvusController.cs     # Unified controller (WebSocket + Whisper + LMCC + TTS)
│   │   │   │   ├── WebSocketClient.cs      # WebSocket connection to Python
│   │   │   │   ├── CorvusTTS.cs            # TTS wrapper for Piper
│   │   │   │   └── LMCC.cs                 # Socket.IO client to Mission Control
│   │   │   ├── AstronautController/
│   │   │   │   ├── Astronaut.cs            # Astronaut data model
│   │   │   │   ├── AstronautInstance.cs    # Singleton for global astronaut access
│   │   │   │   ├── AstronautTypes.cs       # Location, Telemetry, VitalsDetails, Data
│   │   │   │   └── FellowAstronaut.cs      # Buddy astronaut reference
│   │   │   ├── EventSystem/
│   │   │   │   ├── EventBus.cs             # Publish-subscribe event system
│   │   │   │   └── EventTypes.cs           # Event definitions (placeholder)
│   │   │   ├── StateMachine/
│   │   │   │   └── ScreenFlow.cs           # UI state machine (placeholder)
│   │   │   └── ThreadFix/
│   │   │       └── UnityMainThreadDispatcher.cs  # Background thread → main thread
│   │   ├── UI/
│   │   │   └── IntentDisplayUI.cs          # HUD display (intent, confidence, latency)
│   │   ├── Prefabs/
│   │   │   ├── KeyboardInput.cs            # HoloLens virtual keyboard
│   │   │   └── Buttons/
│   │   │       ├── EyeGazeHighlight.cs     # Eye-tracking button feedback
│   │   │       └── ButtonGroup/            # Prefab assets
│   │   └── Testing/
│   │       ├── CorvusTest.cs               # Keyboard test (1-5 keys)
│   │       └── PiperTest.cs                # TTS test (T key)
│   ├── Piper/                              # Piper.unity (modified for Unity 6)
│   │   ├── Scripts/PiperManager.cs         # Updated for Inference Engine 2.4+
│   │   ├── Plugins/Windows/               # espeak-ng.dll, piper_phonemize.dll
│   │   └── Samples/
│   ├── PiperModels/                        # Piper TTS model files
│   │   ├── en_US-lessac-medium.onnx
│   │   └── en_US-lessac-medium.onnx.json
│   └── StreamingAssets/
│       ├── espeak-ng-data/                 # Piper phoneme data
│       └── Whisper/
│           └── ggml-tiny.bin               # Whisper STT model (~75MB)
│
CORVUS_PythonServer/                        # Python AI server
├── server.py                               # WebSocket server
├── ai_model.py                             # AI inference (keyword placeholder → real model)
├── config.py                               # Intent mappings, thresholds, server config
├── pyproject.toml
└── models/                                 # Classifier model files (empty, awaiting teammate)
```

## WebSocket Protocol

**Unity → Python (Command Request)**
```json
{
  "command": "check my vitals"
}
```

**Python → Unity (Intent Response)**
```json
{
  "status": "success",
  "intent": "check_vitals",
  "confidence": 0.87,
  "matched_keywords": ["vitals", "check"],
  "parameters": {},
  "request_id": "abc-123",
  "latency_ms": 2.35,
  "timestamp": "2026-01-18T10:30:00Z"
}
```

**C# Classes (CorvusController.cs):**
```csharp
[System.Serializable]
public class CommandRequest { public string command; }

[System.Serializable]
public class IntentResponse
{
    public string status;
    public string intent;
    public float confidence;
    public string[] matched_keywords;
    public string request_id;
    public float latency_ms;
    public string timestamp;
}
```

## Telemetry Data Model

Access path: `AstronautInstance.User.telemetry.telemetry.eva1` (or `eva2`)

```csharp
// AstronautInstance.User → Astronaut
Astronaut {
    id, name, color
    telemetry → Telemetry → TelemetryDetails {
        eva_time: int
        eva1: VitalsDetails    // This astronaut
        eva2: VitalsDetails    // Fellow astronaut
    }
}

// VitalsDetails - key fields for CORVUS responses
VitalsDetails {
    heart_rate: double
    temperature: double
    batt_time_left: double
    oxy_pri_storage: double
    oxy_sec_storage: double
    oxy_time_left: int
    suit_pressure_total: double
    fan_pri_rpm: double
    coolant_m: double
    // ... and more
}
```

## LMCC Integration

**LMCC** = Local Mission Control Center. Central server connecting all GEMINI clients.

**Sending data to LMCC:**
```csharp
// clientId: 1=EV1, 2=EV2, 3=PR, 4=LMCC
lmcc.SendJsonData(payload, "voice_text", 4);
```

**LMCC message types:** VITALS, WAYPOINTS, MESSAGING, ASTRONAUT, PR_TELEMETRY, PR_LOCATION, LTV_LOCATION, ALERTS, CORVUS

**Note:** The CORVUS case in LMCC.cs HandleJsonMessage() is stubbed but empty — ready for implementation.

## Intent Classification

**Confidence Thresholds:**
- High (>=0.8): Execute immediately
- Medium (0.5-0.8): Execute with confirmation
- Low (<0.5): Retry or fallback

**Sample Commands:**
1. "Check my vitals" → `check_vitals`
2. "Navigate to airlock" → `navigate_to_airlock`
3. "What is my oxygen level" → `check_oxygen_level`
4. "Show battery status" → `check_battery`
5. "Emergency abort" → `emergency_abort`

## Performance Targets

| Metric | Target | Achieved |
|--------|--------|----------|
| Round-trip latency | <1000ms | TBD |
| AI Inference | <350ms | TBD |
| TTS generation | <50ms | ~70ms |
| Whisper STT | <2000ms | TBD |
| Intent accuracy | >95% | TBD |

---

## Implementation Phases & Progress

### ✅ Phase 1-4: Project Setup (COMPLETED)
- [x] Project cleanup and folder structure
- [x] CORVUS scene setup (GameObject, UIBackplate, TextMeshPro, TestCommandButton)
- [x] Python server structure (uv project, server.py, ai_model.py, config.py)

### ✅ Phase 5: Piper.unity TTS Integration (COMPLETED)

**Goal**: Local TTS feedback using Piper.unity | **Achieved**: ~70ms after warmup

#### Step 5.1: Install Unity Sentis ✅
- [x] Installed `com.unity.ai.inference` (Sentis 2.4.1 / Inference Engine)

#### Step 5.2: Install Piper.unity ✅
- [x] Downloaded from https://github.com/Macoron/piper.unity
- [x] Copied `Assets/Piper/` and `Assets/StreamingAssets/espeak-ng-data/`
- [x] Unity API Updater applied for deprecated calls
- [x] **Manually migrated PiperManager.cs for Unity 6 compatibility:**
  - Namespace: `Unity.Sentis` → `Unity.InferenceEngine`
  - Worker: `IWorker` → `Worker`, `WorkerFactory.CreateWorker()` → `new Worker()`
  - Tensors: `TensorFloat`/`TensorInt` → `Tensor<float>`/`Tensor<int>`
  - Execution: `Execute(dict)` → `SetInput()` + `Schedule()`
  - Readback: `MakeReadableAsync()` → `ReadbackAndCloneAsync()`
  - Data: `ToReadOnlyArray()` → `AsReadOnlyNativeArray().ToArray()`

#### Step 5.3: Download Voice Model ✅
- [x] Downloaded `en_US-lessac-medium.onnx` (39MB) + `.onnx.json` config
- [x] Placed in `Assets/PiperModels/`
- [x] Config: sample_rate=22050, voice=en-us

#### Step 5.4: Create CorvusTTS.cs ✅
- [x] Wrapper with `Speak(text)`, `Stop()`, `IsSpeaking()`, `Warmup()`
- [x] Auto-warmup on Start()
- [x] Latency logging via Stopwatch

#### Step 5.5: Test TTS Standalone ✅
- [x] PiperTest.cs: Press T key to test
- [x] First run ~2800ms → warmed up ~70ms

#### Step 5.6: Integrate with CorvusController ✅
- [x] Added CorvusTTS SerializeField to CorvusController
- [x] `GetResponseForIntent()` maps intents to spoken phrases
- [x] TTS called in `HandleMessageReceived()` after intent parsing

### ✅ Phase 6-7: Unity Scripts & Scene Wiring (COMPLETED)
- [x] Created: WebSocketClient.cs, CorvusController.cs, IntentDisplayUI.cs, CorvusTest.cs
- [x] All scripts attached and SerializeField references connected in Inspector
- [x] New Input System: `Keyboard.current.digitXKey.wasPressedThisFrame`

### ✅ Phase 8-9: Python Server & Integration (COMPLETED)
- [x] WebSocket server running on port 8765
- [x] JSON message parsing (Unity sends `{"command":"..."}`, Python responds with intent)
- [x] End-to-end tested: Unity → Python → Intent → UI Update + TTS

### ✅ Phase 9.5: Merge Main into Branch (COMPLETED)
- [x] Merged `origin/main` into `AI-integration-piper-tts` (--allow-unrelated-histories)
- [x] Unity files (scenes, prefabs, .meta, ProjectSettings): kept main's version
- [x] Shared team code (AstronautController, EventSystem, StateMachine, etc.): kept main's version
- [x] CorvusController.cs conflict: main had Molly's VoiceAssistant at same path
- [x] Re-added `com.unity.ai.inference` to manifest.json (was removed by main's version)
- [x] Re-enabled "Allow unsafe code" in Player Settings (was reset by main's version)
- [x] Resolved all compilation errors in Safe Mode

**Files gained from main:**
- LMCC.cs (Socket.IO client to mission control)
- Astronaut.cs, AstronautInstance.cs, AstronautTypes.cs, FellowAstronaut.cs
- EventBus.cs, EventTypes.cs
- UnityMainThreadDispatcher.cs
- ScreenFlow.cs, EyeGazeHighlight.cs, KeyboardInput.cs

**Merge notes:**
- Molly's `VoiceAssistant` class (in main's CorvusController.cs) uses Windows `KeywordRecognizer` + `DictationRecognizer` — different approach from ours
- Her approach sends transcripts to LMCC via Socket.IO; ours sends to Python via WebSocket
- Decision: Unify both approaches into one CorvusController (Phase 10)
- Teammate has Whisper implementation on `origin/Whisper` branch (Jan 25, 2026 commit)

### 🔄 Phase 10: Unified Controller + Real Classifier (IN PROGRESS)

**Goal**: Combine all approaches into one CorvusController with real telemetry responses

#### Step 10.1: Integrate Classifier into Python Server
- [ ] Receive classifier model from teammates (have `referencemodel.pth` — DistilBERT, 6 classes)
- [ ] Integrate model into `ai_model.py`
- [ ] Update `server.py` to use real classifier
- [ ] Test classification accuracy with sample commands
- [ ] Verify response format matches IntentResponse class

#### Step 10.2: Rewrite CorvusController.cs (Unified) ✅
- [x] Combine: WebSocket/Python pipeline + Whisper STT + LMCC logging + telemetry responses
- [x] Add SerializeFields: WhisperManager, MicrophoneRecord, LMCC
- [x] Add Whisper callbacks (OnRecordStop → transcribe → SendCommandAsync)
- [x] Add LogToLMCC() for mission coordination (graceful null handling)
- [x] Add StartRecording()/StopRecording() public methods
- [x] Add wake word detection ("hey corvus", "corvus") via KeywordRecognizer
- [x] Add 200ms delay after wake word to prevent first-word cutoff
- [ ] Update GetResponseForIntent() to use AstronautInstance.User.telemetry (pending LMCC data)

#### Step 10.3: Install whisper.unity Package ✅
- [x] Install whisper.unity from GitHub (`com.whisper.unity`)
- [x] Downloaded `ggml-tiny.bin` model (~75MB) to `Assets/StreamingAssets/Whisper/`
- [x] Verified package works with Unity 6 — no migration needed (unlike Piper)

#### Step 10.4: Scene Wiring ✅
- [x] Add WhisperManager + MicrophoneRecord components to CORVUS GameObject
- [x] Configure WhisperManager model path
- [x] Wire WhisperManager and MicrophoneRecord SerializeField references
- [x] Enable VAD (Voice Activity Detection) for auto-stop on silence
- [ ] Wire LMCC reference to CorvusController (optional, skipped for now)

#### Step 10.5: End-to-End Testing ✅
- [x] Test wake word ("corvus") → recording starts
- [x] Test Whisper mic → transcription → Python classification → TTS response
- [x] Test keyboard input (1-5 keys via CorvusTest) — needs verification
- [ ] Test telemetry responses with LMCC data (pending)
- [ ] Measure end-to-end latency

### 📋 Phase 11: Text Input UI + Polish (NEXT)
- [ ] Add TMP_InputField for typed commands (fallback input method)
- [ ] Wire InputField submit to CorvusController.SendCommandAsync()
- [ ] Add recording indicator UI for Whisper
- [ ] Test all input methods: keyboard shortcuts, text field, voice

### 📋 Phase 12: Optimization & Deployment (FUTURE)
- [ ] Optimize latency across full pipeline
- [ ] Test on HoloLens 2
- [ ] Jetson Orin Nano deployment
- [ ] Final performance benchmarks

---

## CORVUS GameObject Components

The CORVUS GameObject in the scene has:
- **CorvusController** - Unified controller (WebSocket + Whisper + Wake Word + LMCC + TTS)
- **CorvusTTS** - TTS wrapper (references PiperManager + AudioSource)
- **PiperManager** - Neural TTS model inference (Backend: GPUCompute)
- **WhisperManager** - Whisper STT model inference (ggml-tiny.bin)
- **MicrophoneRecord** - Audio recording for Whisper (VAD enabled)
- **CorvusTest** - Keyboard shortcuts (1-5 keys for test commands)
- **PiperTest** - TTS test (T key)
- **AudioSource** - Audio playback

**Other Scene Objects:**
- **AstronautInstance** - Singleton providing global astronaut telemetry access
- **LMCC** - Socket.IO client (on separate GameObject, not yet wired to CorvusController)
- **UnityMainThreadDispatcher** - Thread safety for Socket.IO callbacks

## Known Issues

1. **Piper.unity + Unity 6**: Required manual API migration (documented in Step 5.2)
2. **First TTS Call Slow**: ~2800ms on first run due to GPU shader compilation. Mitigated by `Warmup()` on Start
3. **Input System**: Project uses new Input System. Use `Keyboard.current` not `Input.GetKeyDown()`
4. **Whisper first-word cutoff**: Fixed with 200ms delay after wake word detection in `OnWakeWordDetected()`
5. **LMCC.cs switch warning**: CS8509 warning about exhaustive switch — safe to ignore, only uses clientIds 1-4
6. **Classifier model not integrated**: Have `referencemodel.pth` (DistilBERT) but not yet loaded — using keyword classifier

## Development Notes

- Python server must run before Unity Play
- Use **uv** for Python package management
- Unity 6 renamed Sentis to "Inference Engine" (`com.unity.ai.inference`)
- Always test with Console window open for debug logs
- TTS warmup curve: ~2800ms → ~600ms → ~350ms → ~70ms (stabilizes after ~10 runs)
- Windows file system is case-insensitive (learned during merge)
- LMCC uses Newtonsoft.Json (not Unity's JsonUtility) for complex JSON
- Whisper model location: `Assets/StreamingAssets/Whisper/ggml-tiny.bin`
- Wake words: "hey corvus", "corvus" — triggers recording via KeywordRecognizer
- VAD (Voice Activity Detection) auto-stops recording when user stops speaking
- Deleted: `CorvusController_OLD.cs` (Molly's VoiceAssistant — replaced by unified controller)

## Teaching Preferences

- **Step-by-step**: Break tasks into small steps, explain as we go
- **Bug hunting**: State number of bugs found, let developer search first
- **Concepts over code**: Explain what/why/when, not just how
- **Code review**: Always check for case sensitivity, null checks, missing usings, disposal patterns
