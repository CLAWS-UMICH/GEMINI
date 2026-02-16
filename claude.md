# CORVUS AI Assistant - Project Context

## Overview

CORVUS is an AI voice assistant for NASA's Project GEMINI EVA operations. Astronauts wear HoloLens 2 headsets; a Jetson Orin Nano (8GB) in the suit handles AI processing. The system uses dual-inference: simple commands run locally, complex queries route to cloud.

## Architecture

```
HoloLens 2                        Jetson Orin Nano                    Cloud
───────────────────────────────────────────────────────────────────────────
Mic → Audio ──WebSocket──→ Whisper STT → Classifier → Router
                                                         ↓
                                              ┌─────────┴─────────┐
                                           Simple              Complex
                                              ↓                    ↓
                                         Template            FAISS/RAG
                                         Response          → Claude API
                                              ↓                    ↓
Piper TTS ← Speaker ←─────────────────── Response ←────────────────┘
```

### Device Responsibilities

| HoloLens 2 (4GB) | Jetson Orin Nano (8GB) | Cloud |
|------------------|------------------------|-------|
| Mic recording | Whisper STT | Claude/GPT API |
| Piper TTS | MiniLM embeddings | Complex reasoning |
| Unity AR/UI | Intent classifier (NN) | — |
| Wake word detection | Routing NN | — |
| — | FAISS vector store | — |
| — | Context management | — |

### Communication

- **HoloLens ↔ Jetson**: WebSocket (ws://[jetson-ip]:8765) over local WiFi
- **Jetson ↔ Cloud**: HTTPS (requires internet)
- **Unity ↔ LMCC**: Socket.IO (mission control telemetry)

## Current State (Working)

- Unity project structure with CORVUS scene
- Wake word detection ("hey corvus") via KeywordRecognizer
- Whisper STT (whisper.unity, ggml-tiny model)
- WebSocket connection to Python server
- Keyword-based classifier (placeholder for real model)
- Piper TTS (~70ms after warmup)
- LMCC integration structure (Socket.IO)
- Full latency tracking UI (STT, classification, network, round-trip, TTS, total) via CorvusLatency class

## Dual-Inference Pipeline

### Local Path (<400ms target)
Simple commands with high confidence. Returns template responses.

Examples: "check my vitals", "navigate to airlock", "set timer"

### Cloud Path (<1500ms target)
Complex queries, low confidence, or context-dependent. Uses RAG retrieval + Claude API.

Examples: "is that normal?", "what should I do if oxygen drops?", "explain the procedure"

### Routing Logic
Route to cloud when:
- Confidence below 75%
- Intent is complex (EXPLAIN, COMPARE, QUESTION)
- Contains anaphora ("that", "it", "this")
- Out-of-distribution query

## Classifier Architecture

### Current: DistilBERT (to be replaced)
- ~263MB, ~50-100ms latency
- Overkill for 200-500 fixed intents

### Planned: MiniLM Embeddings + Neural Network
- MiniLM (all-MiniLM-L6-v2) converts text to 384-dim vector (shared with RAG)
- Simple 2-layer NN classifies intent (~5-15ms)
- Separate routing NN decides local vs cloud

```
Input text
    ↓
MiniLM (encoder-only transformer) → 384-dim embedding
    ↓
NN: Linear(384→128) → ReLU → Dropout → Linear(128→num_intents)
    ↓
Softmax → intent probabilities
```

### SetFit for Few-Shot Training
SetFit is a HuggingFace few-shot fine-tuning framework ideal for CORVUS:
- Fine-tunes MiniLM using **contrastive learning** (pulls same-class embeddings together, pushes different-class apart)
- Requires only **8-16 labeled examples per intent**
- Trains in ~30 seconds
- Achieves **90-95% accuracy** with minimal data
- No prompts needed (unlike GPT-based few-shot)
- **Perfect for EVA commands** where labeled data is limited

### MiniLM vs DistilBERT

| Model | Size | Output | Inference |
|-------|------|--------|-----------|
| MiniLM | ~80-100MB | 384-dim embedding | ~5-10ms |
| DistilBERT | ~260MB | 768-dim + classification | ~50-100ms |

MiniLM is ~3x smaller and ~5-10x faster.

### NN Optimizations (Phased)
1. Basic intent NN + rule-based routing
2. Confidence thresholding, shortcut cache, OOD detection
3. Multi-task head (intent + route + urgency)
4. Learned routing NN
5. Temperature calibration

## Python Server Structure

```
CORVUS_PythonServer/
├── models/
│   ├── embeddings/minilm/
│   ├── classifier/intent_nn.pt, routing_nn.pt
│   └── whisper/base.en/
├── data/
│   ├── intents/training_data.json, shortcuts.json
│   ├── rag/eva_procedures/, faiss_index/
│   └── logs/
├── src/
│   ├── server/main.py, websocket_handler.py
│   ├── stt/whisper_transcriber.py
│   ├── classifier/embedder.py, intent_classifier.py, routing_classifier.py
│   ├── rag/vector_store.py, knowledge_graph.py, retriever.py
│   ├── cloud/api_client.py, prompt_builder.py
│   ├── context/context_window.py, anaphora_detector.py
│   └── pipeline/router.py, local_handler.py, cloud_handler.py
├── scripts/train_intent_nn.py, build_faiss_index.py
└── tests/
```

## Unity Project Structure

```
CORVUS_Integration/Assets/CLAWS/
├── Backend/
│   ├── Networking/
│   │   ├── CorvusController.cs    # Unified controller
│   │   ├── WebSocketClient.cs     # Python connection
│   │   ├── CorvusTTS.cs           # Piper wrapper
│   │   └── LMCC.cs                # Mission control
│   └── AstronautController/       # Telemetry data
├── UI/IntentDisplayUI.cs
└── Testing/CorvusTest.cs, PiperTest.cs
```

## WebSocket Protocol

**Unity → Python**
```json
{"command": "check my vitals"}
```

**Python → Unity**
```json
{
  "status": "success",
  "intent": "check_vitals",
  "confidence": 0.92,
  "route": "local",
  "response": "Heart rate 72, oxygen 98 percent"
}
```

## Hardware Constraints

| Device | RAM | ML Capability |
|--------|-----|---------------|
| HoloLens 2 | 4GB | Limited (AR takes priority) |
| Jetson Orin Nano | 8GB | Whisper small, MiniLM, NN classifier, FAISS |

### Whisper Options for Jetson

| Model | RAM | Latency | Recommended |
|-------|-----|---------|-------------|
| tiny.en | ~1GB | ~100-150ms | ✅ Start here |
| base.en | ~1GB | ~150-250ms | ✅ Good balance |
| small.en | ~2GB | ~300-500ms | ⚠️ If accuracy needed |

## Implementation Phases

### ✅ Completed
- Unity project setup, scene structure
- Piper TTS integration (~70ms)
- Whisper STT (whisper.unity)
- WebSocket communication
- Wake word detection
- Basic keyword classifier

### 🔄 In Progress
- Integrate DistilBERT classifier from teammates
- Real telemetry responses via LMCC

### 📋 Next
- Replace DistilBERT with MiniLM + NN classifier (using SetFit for training)
- Implement routing logic (local vs cloud)
- Build FAISS index for EVA procedures
- Integrate Claude API for complex queries
- Move Whisper from HoloLens to Jetson (see STT Migration Plan below)
- End-to-end testing on hardware

## STT Migration Plan: HoloLens → Jetson

### Current State
- Whisper runs on HoloLens CPU via whisper.unity (ggml-tiny.en)
- STT latency: ~600-700ms (biggest bottleneck)
- VAD enabled in whisper.unity (vadStopTime=1.0s, Silero-style energy-based)
- Pipeline: Wake word → Record → VAD stops recording → Whisper transcribes → Send text over WebSocket

### Target State
- Unity becomes thin audio capture + playback layer
- Jetson handles VAD + STT + classification in one pipeline
- Pipeline: Wake word → Stream raw audio over WebSocket → Jetson VAD + faster-whisper (streaming) → Classify → Respond

### Estimated Latency Improvement

| Component | Current (HoloLens) | Target (Jetson) |
|-----------|-------------------|-----------------|
| VAD silence wait | ~1000ms | ~300-500ms (Silero VAD, tuned) |
| Whisper STT | ~600-700ms (CPU) | ~50-100ms (GPU, faster-whisper) |
| STT overlap | None (batch) | Streaming — transcribes during speech |
| **After-speech → response** | **~650ms** | **~100-150ms** |

### Responsibility Split After Migration

| Component | Unity (HoloLens) | Jetson |
|-----------|-----------------|--------|
| Wake word detection | Yes (KeywordRecognizer) | — |
| Mic capture | Yes | — |
| Audio streaming | Yes (raw PCM over WebSocket) | — |
| VAD | — | Yes (Silero VAD via faster-whisper) |
| STT | — | Yes (faster-whisper, GPU, streaming) |
| Classification | — | Yes |
| TTS | Yes (Piper, ~70ms) | — |

### WebSocket Protocol Change

Current: Unity sends text after local STT
```json
{"command": "check my vitals"}
```

After migration: Unity streams raw PCM audio bytes after wake word, Jetson returns intent response when speech ends.

### Key Libraries (Jetson)
- **faster-whisper** (CTranslate2 backend) — optimized Whisper for GPU
- **Silero VAD** — built into faster-whisper, ~2ms per frame
- Streaming transcription support — chunked inference while user speaks

### Migration Phases
1. Tune current VAD (reduce vadStopTime to 0.3-0.5s) — quick win, no architecture change
2. Add faster-whisper + Silero VAD to Python server
3. Update WebSocket protocol to accept audio streams
4. Update Unity to stream raw mic audio instead of running local Whisper
5. Enable streaming transcription (overlap recording + inference)
6. Evaluate upgrading to base.en or small.en on Jetson GPU

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Classifier | MiniLM + NN over DistilBERT | Faster, smaller, shares embeddings with RAG |
| Few-shot training | SetFit | 8-16 examples/intent, ~30s training, 90-95% accuracy |
| Vector store | FAISS | Perfect for 500 docs, 10-30ms queries, 5MB |
| RAG framework | LangChain | Industry standard, good memory management |
| Whisper location | Jetson (not HoloLens) | HoloLens 4GB too tight with AR running |
| TTS location | HoloLens | Already integrated, lightweight |

## Performance Targets

| Metric | Target |
|--------|--------|
| Local path (simple commands) | <400ms |
| Cloud path (complex queries) | <1500ms |
| Whisper STT | <300ms |
| NN classification | <20ms |
| TTS generation | <100ms |

## Development Notes

- Python server must run before Unity Play
- Use **uv** for Python package management
- Unity 6 renamed Sentis to "Inference Engine"
- TTS warmup: first call ~2800ms, stabilizes to ~70ms
- Train NN in Jupyter, export .pt file to server
- Log routing decisions for future training data

## Teaching Preferences

- Step-by-step task breakdown
- Concepts over code dumps
- State bugs found, let developer search first
- Do not edit code directly; guide me through terminal commands