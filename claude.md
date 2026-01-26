# CORVUS AI Assistant - Project Context

## Project Overview
CORVUS is an AI voice assistant for NASA's Project GEMINI EVA operations, running on HoloLens 2. Provides real-time intent classification, text-to-speech feedback, and AR display for astronaut commands during spacewalks.

## Architecture

### Pipeline Flow
```
User Input → Unity (Text/STT) → WebSocket → Python Server (AI Classifier)
→ Intent Classification → WebSocket Response → Unity → UI Update + TTS Response
```

### Component Communication
- **Unity ↔ Python**: WebSocket (ws://localhost:8765)
- **Unity ↔ LMCC/TSS/MongoDB**: WebSocket
- **TTS**: Piper.unity (local, ~70ms after warmup)
- **AI**: Real classifier model (Python server)

## System Requirements

### Unity
- Version: **Unity 6 (6000.2.7f2)**
- AI Framework: **Inference Engine 2.4.1** (formerly Sentis)
- Required: TextMeshPro, WebSocket (.NET Standard 2.1), Input System Package
- Player Settings: "Allow unsafe code" enabled, Active Input Handling set to "Both"

### Python
- Version: 3.9+
- Package Manager: **uv**
- Libraries: FastAPI, uvicorn, websockets, torch/transformers

### Hardware
- Development: Windows PC with GPU
- Target: HoloLens 2
- Edge Compute: NVIDIA Jetson Orin Nano (recommended)

## Project Structure

```
CORVUS_Integration/                     # Unity project
├── Assets/
│   ├── CLAWS/
│   │   ├── Backend/Networking/
│   │   │   ├── CorvusController.cs     # Main controller (WebSocket + TTS)
│   │   │   ├── WebSocketClient.cs      # WebSocket connection
│   │   │   └── CorvusTTS.cs            # TTS wrapper for Piper
│   │   ├── UI/
│   │   │   └── IntentDisplayUI.cs      # HUD display
│   │   └── Testing/
│   │       ├── CorvusTest.cs           # Keyboard test (1-5 keys)
│   │       └── PiperTest.cs            # TTS test (T key)
│   ├── Piper/                          # Piper.unity (modified for Unity 6)
│   │   ├── Scripts/PiperManager.cs     # Updated for Inference Engine 2.4+
│   │   ├── Plugins/Windows/            # espeak-ng.dll, piper_phonemize.dll
│   │   └── Samples/
│   ├── PiperModels/                    # Voice model files
│   │   ├── en_US-lessac-medium.onnx
│   │   └── en_US-lessac-medium.onnx.json
│   └── StreamingAssets/espeak-ng-data/ # Phoneme data
│
CORVUS_PythonServer/                    # Python AI server
├── server.py                           # WebSocket server
├── ai_model.py                         # AI inference
├── config.py
├── pyproject.toml
└── models/                             # Classifier model files
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

I'm working on the CORVUS AI Voice Assistant project for NASA EVA operations (Unity + Python).                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                      
  Please read CLAUDE.md for full project context, architecture, progress, and teaching preferences.

  Summary of where we are:
  - Phases 1-9 are COMPLETE (project setup, WebSocket communication, TTS integration)
  - Piper.unity TTS is working (~70ms after warmup) with Unity 6 / Inference Engine 2.4.1
  - Unity ↔ Python WebSocket communication is working (port 8765, JSON protocol)
  - We're starting Phase 10: Real Classifier Model Integration

  What I need to do next:
  1. Integrate the real classifier model from my teammates into the Python server (ai_model.py / server.py)
  2. Add a text input UI (InputField) in Unity so I can type commands instead of using keyboard shortcuts (1-5 keys)
  3. Later, replace text input with Whisper voice input (Phase 11)

  Important notes:
  - I'm learning C# and Unity - guide me step by step and let me write the code myself
  - Unity version: 6000.2.7f2 (Unity 6)
  - Project uses the new Input System (not legacy Input)
  - Python uses uv for package management
  - Check CLAUDE.md for the WebSocket protocol format and C# classes
```

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

### 🔄 Phase 10: Real Classifier Model Integration (IN PROGRESS)

**Goal**: Replace mock classifier with real AI model from teammates

#### Step 10.1: Integrate Classifier into Python Server
- [ ] Receive classifier model from teammates
- [ ] Integrate model into `ai_model.py`
- [ ] Update `server.py` to use real classifier
- [ ] Test classification accuracy with sample commands
- [ ] Verify response format matches IntentResponse class

#### Step 10.2: Add Text Input UI in Unity
- [ ] Add InputField to CORVUS scene for text commands
- [ ] Wire InputField submit to CorvusController.SendCommandAsync()
- [ ] Test sending typed commands to Python server
- [ ] Verify intent response and TTS playback

#### Step 10.3: End-to-End Testing with Real Model
- [ ] Test all sample commands with real classifier
- [ ] Measure classification accuracy
- [ ] Measure end-to-end latency
- [ ] Fix any integration issues

### 📋 Phase 11: Voice Input via Whisper (FUTURE)
- [ ] Integrate Whisper STT for voice-to-text
- [ ] Replace text input with voice input
- [ ] Test full voice pipeline: Speech → STT → WebSocket → Intent → TTS

### 📋 Phase 12: Optimization & Deployment (FUTURE)
- [ ] Optimize latency across full pipeline
- [ ] Test on HoloLens 2
- [ ] Jetson Orin Nano deployment
- [ ] Final performance benchmarks

---

## CORVUS GameObject Components

The CORVUS GameObject in the scene has:
- **CorvusController** - WebSocket connection + intent handling
- **CorvusTTS** - TTS wrapper (references PiperManager + AudioSource)
- **PiperManager** - Neural TTS model inference (Backend: GPUCompute)
- **CorvusTest** - Keyboard shortcuts (1-5 keys for test commands)
- **PiperTest** - TTS test (T key)
- **AudioSource** - Audio playback

## Known Issues

1. **Piper.unity + Unity 6**: Required manual API migration (documented in Step 5.2)
2. **First TTS Call Slow**: ~2800ms on first run due to GPU shader compilation. Mitigated by `Warmup()` on Start
3. **Input System**: Project uses new Input System. Use `Keyboard.current` not `Input.GetKeyDown()`

## Development Notes

- Python server must run before Unity Play
- Use **uv** for Python package management
- Unity 6 renamed Sentis to "Inference Engine" (`com.unity.ai.inference`)
- Always test with Console window open for debug logs
- TTS warmup curve: ~2800ms → ~600ms → ~350ms → ~70ms (stabilizes after ~10 runs)

## Teaching Preferences

- **Step-by-step**: Break tasks into small steps, explain as we go
- **Bug hunting**: State number of bugs found, let developer search first
- **Concepts over code**: Explain what/why/when, not just how
- **Code review**: Always check for case sensitivity, null checks, missing usings, disposal patterns
