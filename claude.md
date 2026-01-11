# CORVUS AI Assistant - Project Context

## Project Overview
CORVUS is an AI voice assistant for NASA's Project GEMINI EVA operations, running on HoloLens 2. This system provides real-time intent classification, text-to-speech feedback, and AR display for astronaut commands during spacewalks.

## Architecture

### High-Level Flow
```
User Voice Input → HoloLens Microphone → Unity (STT)
→ WebSocket → Python Server (AI Model) → Intent Classification
→ WebSocket Response → Unity → Execute Action + TTS Response
```

### Dual-Inference Architecture
1. **Local Inference (Jetson Orin Nano)**: Lightweight models (TinyBERT, MiniLM), <350ms latency, handles time-critical/safety commands
2. **Cloud Inference**: Commercial APIs (OpenAI, Azure, Groq) for complex queries when bandwidth permits

### Component Communication
- **Unity ↔ Python**: WebSocket (persistent connection)
- **Unity ↔ LMCC**: WebSocket
- **Unity ↔ TSS**: WebSocket
- **Unity ↔ MongoDB**: WebSocket (telemetry/navigation)
- **DSPy**: Orchestration framework for multi-step reasoning
- **Instructor**: Type-safe output validation via Pydantic

## System Requirements

### Unity
- Version: 2022.3.62f3+
- Platform: Windows (testing), HoloLens 2 (deployment)
- Required: Sentis (AI inference), TextMeshPro, WebSocket support (.NET Standard 2.1)

### Python
- Version: 3.9+
- Package Manager: **uv** (fast Rust-based package installer)
- Libraries: FastAPI, uvicorn, websockets, torch/transformers, onnxruntime

### Hardware
- Development: Windows PC with GPU
- Target: HoloLens 2
- Edge Compute: NVIDIA Jetson Orin Nano (recommended for AI inference)

## Hardware Limitations (HoloLens 2)

### Critical Constraints
- **CPU**: Qualcomm Snapdragon 850 (ARM, 8 cores @ 2.96 GHz) - significantly weaker than desktop
- **RAM**: 4GB total (~2-3GB available to apps)
- **GPU**: Adreno 630 (graphics-focused, no ML accelerators)
- **Battery**: 2-3 hours normal use, drains faster with continuous inference

### Model Performance Expectations (On-Device)
| Model | Parameters | Expected Latency | Feasible? |
|-------|-----------|------------------|-----------|
| TinyBERT | 14M | 200-400ms | ✅ Yes |
| MiniLM-L6 | 22M | 300-500ms | ✅ Marginal |
| DistilBERT | 66M | 800-1500ms | ⚠️ Too slow |

**Recommendation**: Run AI inference on Jetson Orin Nano, use HoloLens as thin client for AR rendering and audio I/O.

## Project Structure

```
CORVUS_Integration/                    # Unity project
├── Assets/CLAWS/
│   ├── Backend/
│   │   ├── Networking/                # WebSocket + CORVUS controller
│   │   ├── AstronautController/       # Existing systems
│   │   ├── EventSystem/
│   │   ├── StateMachine/
│   │   └── ThreadFix/
│   ├── UI/                            # Intent Display UI
│   ├── Testing/                       # Test utilities
│   ├── Prefabs/                       # UI components
│   └── MyProgress/                    # Saved ORA work
│
CORVUS_PythonServer/                   # Python AI server (separate)
├── server.py                          # WebSocket server
├── ai_model.py                        # AI inference
├── config.py
├── pyproject.toml                     # uv project configuration
└── models/                            # AI model files (.onnx)
```

## Key Implementation Details

### WebSocket Message Format

**Unity → Python (Command Request)**
```json
{
  "command": "check my vitals",
  "request_id": "unique-id-12345",
  "timestamp": "2026-01-11T14:30:00Z",
  "user_id": "astronaut_1"
}
```

**Python → Unity (Intent Response)**
```json
{
  "status": "success",
  "intent": "check_vitals",
  "confidence": 0.95,
  "parameters": {},
  "request_id": "unique-id-12345",
  "latency_ms": 250
}
```

### Intent Classification System

**Constrained to 200-500 predefined intents** to prevent hallucination:
- Navigation commands (50-80 intents)
- Suit system queries (80-100 intents)
- Telemetry requests (40-60 intents)
- Emergency protocols (20-30 intents)
- Procedural assistance (30-50 intents)

**Example Intents**: `check_vitals`, `navigate_to_airlock`, `check_oxygen_level`, `emergency_abort`, `show_battery_level`

**Confidence Thresholds**:
- High (≥0.8): Execute immediately
- Medium (0.5-0.8): Execute with confirmation
- Low (<0.5): Trigger retry or fallback

### Text-to-Speech (Piper.unity)
- Generation time: 20-30ms on CPU
- Local, high-quality speech (no internet required)
- Multiple voices and languages

### Latency Measurement

**Pipeline Stages**:
1. T0: User finishes speaking
2. T1: Unity sends WebSocket message
3. T2-T3: Python receives + AI inference
4. T4-T5: Python sends + Unity receives
5. T6: Unity executes action + displays

**Target Breakdown** (Total: <1000ms):
- Speech-to-Text: 300-500ms
- WebSocket send/receive: 5-10ms each
- AI Inference: 100-350ms
- Action execution: 50-100ms
- TTS generation: 20-50ms

## AI Model Recommendations

### Recommended Models
1. **TinyBERT-4**: 14M params, 200-400ms on HoloLens (if on-device needed)
2. **MiniLM-L6**: 22M params, better accuracy, best for Jetson Orin Nano
3. **DistilBERT**: 66M params, 50-100ms on Jetson (too heavy for HoloLens)

### Optimization Strategies
- Quantization: INT8 (4x smaller, 2-4x faster)
- Pruning: Remove 30-50% of weights
- ONNX Runtime: Optimized inference engine
- Knowledge Distillation: Train smaller custom model

## Performance Targets

| Metric | Target | Critical? |
|--------|--------|-----------|
| Round-trip latency | <1000ms | Yes |
| Local inference | <350ms | Yes |
| Intent accuracy | >95% | Yes |
| TTS generation | <50ms | No |
| Battery impact | <15%/hour | Yes |
| Memory footprint | <500MB | Yes |

## Safety Considerations

1. **Confirmation for Critical Commands**: All safety-critical intents require verbal confirmation
2. **Hallucination Prevention**: Constrained to predefined intents, factual outputs grounded in live telemetry
3. **Network Reliability**: Local inference for safety-critical commands, graceful degradation during network loss

## Implementation Phases & Progress

### ✅ Phase 1: Project Cleanup (COMPLETED)
- [x] Remove onboarding folders (ORA, Phase-1/2/3)
- [x] Save progress work to MyProgress folder
- [x] Organize clean project structure

### ✅ Phase 2: Unity Folder Structure (COMPLETED)
- [x] Create `Backend/Networking/` folder
- [x] Create `UI/` folder
- [x] Create `Testing/` folder
- [x] Create `Scenes/` folder

### ✅ Phase 3: CORVUS Scene Setup (COMPLETED)
- [x] Create CORVUS_Test_Scene
- [x] Add CORVUS GameObject with Audio Source
- [x] Add UIBackplate prefab (3D floating display)
- [x] Add 3D TextMeshPro elements (IntentText, ConfidenceText, LatencyText)
- [x] Add TestCommandButton
- [x] Add scene to Build Profiles
- [x] Position UI in front of camera

### ✅ Phase 4: Python Server Structure (COMPLETED)
- [x] Create `CORVUS_PythonServer/` folder
- [x] Initialize uv project (uv init)
- [x] Create `pyproject.toml`
- [x] Create `config.py`
- [x] Create `server.py` (basic structure)
- [x] Create `ai_model.py` (placeholder)
- [x] Create `models/` folder
- [x] Install dependencies with uv

### ⏸️ Phase 5: Install Piper.unity (TTS) (SKIPPED - TO REVISIT)
- [ ] Install Piper.unity via Package Manager
- [ ] Verify installation
- [ ] Test basic TTS functionality

**Note:** Skipping TTS for now to focus on core WebSocket functionality. Will revisit after testing Unity-Python communication.

### ✅ Phase 6: Create Unity Scripts (COMPLETED)
- [x] Create `WebSocketClient.cs` (Backend/Networking/)
- [x] Create `CorvusController.cs` (Backend/Networking/)
- [x] Create `IntentDisplayUI.cs` (UI/)
- [x] Create `CorvusTest.cs` (Testing/)

### ✅ Phase 7: Wire Up Unity Scene (COMPLETED)
- [x] Attach CorvusController script to CORVUS GameObject
- [x] Attach IntentDisplayUI script to UIBackplate GameObject
- [x] Attach CorvusTest script to CORVUS GameObject
- [x] Connect all SerializeField references in Inspector:
  - IntentDisplayUI: CorvusController, IntentText, ConfidenceText, LatencyText
  - CorvusTest: CorvusController
- [x] Save scene

### 📋 Phase 8: Implement Python Server
- [ ] Code WebSocket server logic
- [ ] Add basic intent classification (mock/simple)
- [ ] Implement message parsing
- [ ] Add error handling
- [ ] Test server runs locally

### 📋 Phase 9: Testing & Integration
- [ ] Test WebSocket connection (Unity ↔ Python)
- [ ] Test intent classification with sample commands
- [ ] Test TTS responses
- [ ] Test UI updates correctly
- [ ] Measure end-to-end latency
- [ ] Fix bugs and issues

### 📋 Phase 10: Optimization & Documentation
- [ ] Optimize latency if needed
- [ ] Add real AI model (TinyBERT/MiniLM)
- [ ] Document test results
- [ ] Create comprehensive test suite
- [ ] Final testing on all components

## Key Scripts to Implement

1. **CorvusController.cs** (`Backend/Networking/`)
   - Main controller for CORVUS functionality
   - Handles voice input activation
   - Manages TTS responses
   - Coordinates WebSocket and UI

2. **WebSocketClient.cs** (`Backend/Networking/`)
   - WebSocket connection to Python server
   - Send/receive messages
   - Latency measurement

3. **IntentDisplayUI.cs** (`UI/`)
   - Update HUD with intent information
   - Display confidence and latency
   - Color-coded confidence bars

4. **CorvusTest.cs** (`Testing/`)
   - Testing utilities and keyboard shortcuts
   - Sample command testing
   - Latency measurement and logging

## Sample Test Commands

1. "Check my vitals" → `check_vitals`
2. "Navigate to airlock" → `navigate_to_airlock`
3. "What is my oxygen level" → `check_oxygen_level`
4. "Show battery status" → `check_battery`
5. "Emergency abort" → `emergency_abort`

## Known Issues

1. **CorvusController Multiple-Run Issue**: First voice command works, second fails. Need to add proper cleanup in `OnDestroy()` and reset state between commands.

2. **Piper.unity Installation**: Install via Package Manager with git URL: `https://github.com/SCRN-VRC/Piper.Unity.git`

## Resources

- Unity Sentis: https://docs.unity3d.com/Packages/com.unity.sentis@latest
- Piper.unity: https://github.com/SCRN-VRC/Piper.Unity
- FastAPI: https://fastapi.tiangolo.com/
- WebSocket Tutorial: https://youtu.be/8ARodQ4Wlf4
- Hugging Face Models: https://huggingface.co/models

## Development Notes

- Always test locally first (Unity Editor on PC)
- Python server must run before Unity
- Use **uv** for Python package management (faster than pip)
- Version control before major changes
- Log everything during testing
- Measure latency for every change

## Learning Approach & Best Practices

### Teaching Style
1. **Step-by-Step Implementation**: Break down complex tasks into single, manageable steps. Wait for completion confirmation before moving to the next step.
2. **Concept Explanations**: When introducing new syntax or patterns, explain:
   - What it does
   - Why we use it
   - When to use it
   - Analogies to familiar concepts (C++, Python, etc.)
3. **Answer Questions First**: Address all clarifying questions before proceeding to the next step
4. **Examples**: Provide concrete examples and use cases for abstract concepts

### Bug Hunting Practice
When reviewing code for bugs:
1. **Don't reveal locations immediately** - State the number and type of bugs found
2. **Let the developer hunt** - Encourage manual searching to build debugging skills
3. **Provide hints if stuck** - Guide with line numbers or specific areas if needed
4. **Explain the bug** - After finding it, explain why it's wrong and how to fix it

**Example Bug Types to Watch For:**
- Case sensitivity errors (Debug.log → Debug.Log, MonoBehavior → MonoBehaviour)
- Missing property accessors (_text vs _text.text)
- Wrong variable references (ClassName vs _instanceName)
- Array index mismatches
- Missing using statements
- Typos in method names

### Concepts Explained This Session

**C# Fundamentals:**
- **MonoBehaviour**: Unity base class providing lifecycle methods (Start, Update, OnDestroy)
- **async/await**: Non-blocking operations, Task vs Task<T>, async void vs async Task
- **Events & Delegates**: Action<T>, subscribing with +=, unsubscribing with -=
- **Properties**: Expression-bodied members with `=>`, get/set accessors
- **SerializeField**: Makes private fields visible in Unity Inspector
- **Null operators**: `?.` (null-conditional), `??` (null-coalescing), `!` (logical NOT)
- **ArraySegment<T>**: Lightweight array slice without copying data
- **CancellationTokenSource**: Gracefully cancel async operations

**Unity Patterns:**
- **FindObjectOfType vs SerializeField**: Runtime search vs Inspector assignment (prefer SerializeField for clarity and performance)
- **Event subscription patterns**: Subscribe in Start(), unsubscribe in OnDestroy() to prevent memory leaks
- **3D TextMeshPro vs Canvas UI**: World-space 3D text for AR/VR vs 2D screen overlay
- **Prefabs**: Reusable GameObject templates/blueprints
- **Scenes**: Different levels/pages in your application

**Architecture:**
- **WebSocket Communication**: Persistent bidirectional connection (ws://)
- **Event-Driven Design**: Loose coupling via events (WebSocketClient → CorvusController → IntentDisplayUI)
- **Separation of Concerns**: Networking, Controller, UI, Testing in separate scripts
- **SerializeField Pattern**: Inspector-assignable references instead of hardcoded dependencies

### Git Best Practices (CRITICAL)

**Golden Rule: ONE git init per project**
- ✅ Run `git init` ONLY at the project root folder
- ❌ NEVER run `git init` in subfolders (creates nested repositories/submodules)
- ✅ Run `git add .` and `git commit -m "message"` anywhere in the project
- The `.` in `git add .` means "current directory and all subdirectories"

**If you accidentally create a nested repository:**
```bash
# Remove the submodule reference
git rm --cached path/to/subfolder

# Delete the nested .git folder
rm -rf path/to/subfolder/.git

# Remove .gitmodules if it exists
rm -f .gitmodules

# Re-add the files to main repository
git add .
git commit -m "Fix: Remove nested repository"
```

### Testing Philosophy
1. **Test incrementally**: Test each component as you build it
2. **Use keyboard shortcuts**: Create testing utilities (like CorvusTest.cs) for rapid iteration
3. **Log everything**: Use Debug.Log liberally during development
4. **Expect failures**: When testing without server, connection failures are normal and expected

### Code Review Checklist
Before moving to next phase, verify:
- [ ] All using statements present
- [ ] Case sensitivity correct (Unity API is case-sensitive)
- [ ] Property accessors used correctly (.text, .color, etc.)
- [ ] Null checks for optional references
- [ ] Event subscriptions have matching unsubscriptions
- [ ] SerializeField variables will be assigned in Inspector
- [ ] Array indices match array length
- [ ] Async methods properly awaited or fire-and-forget with `_`