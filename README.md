# CORVUS Python Server

Voice → classify → telemetry-grounded response loop for the CLAWS-UMICH suit-and-rover stack. Two modes share one Python package:

- **`corvus-eva`** — Unity-paired. WebSocket server on `:8765`. Unity handles wake word, mic capture, and Piper TTS playback; Python handles Whisper STT, classification, and response text.
- **`corvus-pr`** — standalone. Full audio loop in Python: openWakeWord → Silero VAD → Whisper STT → classify → Piper TTS.

Both modes share the same telemetry source ([stilettocode/TTTDTT](https://github.com/stilettocode/TTTDTT) on `:5001`, which mirrors NASA TSS over UDP) and the same classifier + responder layer.

See `docs/superpowers/specs/2026-05-14-corvus-dual-mode-voice-and-model-swap-design.md` for the full design (gitignored — internal).

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- A running [TTTDTT](https://github.com/stilettocode/TTTDTT) instance reachable at `$TTTDTT_URL` (defaults to `http://localhost:5001`).
- For `corvus-pr`: a working mic + speaker, plus the PortAudio shared library (`sudo apt install libportaudio2` on Debian/Ubuntu/WSL).
- Optional: a CUDA GPU (boosts Whisper from ~700 ms–1.2 s → ~200 ms).

## Setup

```bash
uv sync
./scripts/install_whisper.sh   # downloads base.en checkpoint (~150 MB)
./scripts/install_piper.sh     # downloads en_US-lessac-medium voice (~64 MB)
./scripts/install_wakeword.sh  # verifies bundled openWakeWord models
```

## Run

### EVA mode — `uv run corvus-eva`

Unity-paired. Python boots a WebSocket server on `0.0.0.0:8765`, connects to TTTDTT as a Socket.IO client, loads the classifier, and loads Whisper STT (mandatory).

**Required:**
- TTTDTT reachable (otherwise handlers return "Telemetry unavailable right now.")
- Whisper checkpoint MUST be installed — `main.py` exits with code 1 on startup if `models/stt/whisper-base.en/` is missing. Run `./scripts/install_whisper.sh`.

**Expected boot logs:**
```
multi-label sidecars missing at .../models/multilabel/label2id.json; using legacy NN classifier (mode=eva)
sentence_transformers.SentenceTransformer: Use pytorch device_name: cuda:0   ← or cpu
[SUCCESS] Classifier loaded (NNClassifier)
Loading Whisper from .../whisper-base.en (device=cuda, compute_type=float16)
[SUCCESS] Whisper STT loaded
[SUCCESS] Silero VAD loaded
websockets.server: server listening on 0.0.0.0:8765
[SUCCESS] Server running on ws://0.0.0.0:8765
[INFO] Waiting for Unity connection...
```

**Wire protocol** (streaming PCM contract with Unity — see `STT_UNITY_PYTHON_CONTRACT.md` and `docs/superpowers/specs/2026-05-15-corvus-eva-unity-contract-design.md`):

Unity opens one WebSocket and keeps it open for the session. Text frames carry JSON control messages; binary frames carry raw int16 LE PCM @ 16 kHz mono, ~3200 bytes per ~100ms chunk.

Unity → Python — start utterance (text):
```json
{"type": "start", "sample_rate": 16000, "channels": 1}
```

Unity → Python — audio chunks (binary): raw int16 little-endian samples, no header.

Unity → Python — cancel (text):
```json
{"type": "stop"}
```

Python → Unity — terminal response (text):
```json
{
  "type": "final",
  "response": "Heart rate is 72 beats per minute.",
  "transcript": "check my heart rate",
  "intent": "vitals_heart_rate",
  "confidence": 0.92,
  "parameters": {},
  "latency_ms": 187.0
}
```

`transcript`, `intent`, `confidence`, `parameters`, and `latency_ms` are optional and omitted when not produced. `response` is always present (may be empty string on STT/VAD failure to keep Unity unstuck).

Python emits `{type:"final"}` after Silero VAD detects end-of-speech (default 700ms silence, env `EVA_VAD_HANGOVER_MS`). A 30-second hard cap (env `EVA_MAX_UTTERANCE_S`) forces finalize if VAD never fires.

**Smoke test from Python:**
```bash
EVA_E2E=1 uv run python -m pytest tests/test_eva_handler_e2e.py -v
```

For an ad-hoc text client (no audio), see `tests/test_eva_protocol.py` and `tests/test_eva_session.py` — they exercise the state machine directly with synthetic PCM and `FakeVAD`/`FakeSTT`.

### PR mode — three flavors

PR mode is standalone — no WebSocket server, no Unity. Three operating modes:

| Command                                | Mic | Speaker | Use case                                  |
|----------------------------------------|-----|---------|--------------------------------------------|
| `uv run corvus-pr`                     | ✓   | ✓       | Full voice loop. The demo path.            |
| `uv run corvus-pr --stdin`             |     |         | Type commands, read response text. Debug.  |
| `uv run corvus-pr --stdin --speak`     |     | ✓       | Type commands, hear Piper speak responses. |

**Required for full voice mode (`corvus-pr` with no flags):**
- All install scripts run (`install_whisper.sh`, `install_piper.sh`)
- PortAudio: `sudo apt install libportaudio2`
- Mic and speaker visible to sounddevice — verify with `uv run python -c "import sounddevice; print(sounddevice.query_devices())"`. WSL shows 0 devices by default; you need WSLg's PulseAudio bridge or run on Windows/native Linux for live mic+speaker.
- A wake-word model the detector can load (see "Wake word setup" below)
- TTTDTT reachable (otherwise responses say "Telemetry unavailable")

**Required for `--stdin --speak`:** just the Piper voice + working speaker.

**Required for `--stdin` alone:** just the classifier (already in repo, no downloads).

**Expected boot logs (voice mode):**
```
[INFO] Starting CORVUS-PR Agent…
[INFO] Mode: voice (speak=False)
[INFO] TTTDTT client started (target: http://localhost:5001)
[SUCCESS] Classifier loaded (NNClassifier)
[SUCCESS] Piper TTS loaded
[SUCCESS] Whisper STT loaded
[SUCCESS] Silero VAD loaded
[SUCCESS] openWakeWord loaded
[INFO] Wake word listener active. Say 'hey jarvis' to interact.
```

Then, after a wake-word hit:
```
[SUCCESS] Wake word detected.
[INFO] Listening (VAD-gated)…
[INFO] Heard: 'what is my speed'
[INFO] [get_speed @ 0.99] Current rover speed is 1.42 meters per second.
```

### Wake word setup

`src/voice/wake_word.py` defaults to `DEFAULT_WAKEWORD = "hey_corvus"`. That phrase is **not** in openwakeword 0.4.0's bundled set (which only ships `alexa`, `hey_mycroft`, `hey_jarvis`, `timer`, `weather`), so `corvus-pr` voice mode boot will throw `ValueError: Wake-word 'hey_corvus' not found in bundled models` until you either:

1. **Use a bundled wake word** — quick swap, lower-friction:
   ```python
   # src/voice/wake_word.py
   DEFAULT_WAKEWORD = "hey_jarvis"
   ```
2. **Train a custom `hey_corvus.onnx`** via openWakeWord's [automatic_model_training.ipynb](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb) on Colab (~45 min, free T4, no audio data required — synthetic TTS). Drop the resulting `hey_corvus.onnx` into `models/wake_word/` and pass it explicitly:
   ```python
   # src/modes/pr/main.py
   wake = WakeWordDetector(model_paths=["models/wake_word/hey_corvus.onnx"])
   ```

`--stdin` and `--stdin --speak` skip the wake-word path entirely.

## Mode flows

### EVA mode

```
Unity ──WS─▶ {audio: bytes} or {command: text}
              ↓
         Whisper STT (if audio) ──▶ text
              ↓
         classifier(text)               ⟵ EVA-label mask (Phase 2)
              ↓
         dispatch → response_text ──WS─▶ Unity ──▶ Piper TTS
```

### PR mode

```
idle
  ↓
openWakeWord triggers ("hey jarvis")
  ↓
Silero VAD-gated mic capture
  ↓
Whisper STT ──▶ text
  ↓
classifier(text)                       ⟵ PR-label mask (Phase 2)
  ↓
dispatch → response_text ──▶ Piper TTS ──▶ speaker
  ↓
back to idle
```

## Device routing (CPU vs GPU)

Single decision in `src/voice/devices.py::select_stt_device()`. Logged at boot.

| Component        | GPU path (demo machine)                | CPU path (fallback)               |
|------------------|----------------------------------------|------------------------------------|
| Whisper `base.en`| `device=cuda, compute_type=float16`    | `device=cpu, compute_type=int8`   |
| Classifier       | CPU                                    | CPU                                |
| Piper TTS        | CPU                                    | CPU                                |
| Silero VAD       | CPU                                    | CPU                                |
| openWakeWord     | CPU                                    | CPU                                |

End-to-end latency (end-of-speech → start-of-response audio):

| Path                | Latency       |
|---------------------|---------------|
| GPU Whisper         | ~400–500 ms   |
| CPU `int8` Whisper  | ~700 ms–1.2 s |

To force CPU fallback locally for testing: `CUDA_VISIBLE_DEVICES="" uv run corvus-pr`.

## Environment variables

| Variable                | Default                | Description                                       |
|-------------------------|------------------------|----------------------------------------------------|
| `TTTDTT_URL`            | `http://localhost:5001`| TTTDTT Socket.IO endpoint                          |
| `STALE_TELEMETRY_S`     | `10.0`                 | Seconds before cached telemetry is considered stale |
| `EMIT_VOICESTRING`      | `1`                    | Re-publish `response_text` on TTTDTT `voiceString` |
| `WS_HOST`               | `0.0.0.0`              | EVA WebSocket bind host                            |
| `WS_PORT`               | `8765`                 | EVA WebSocket bind port                            |

## Tests

```bash
uv run python -m pytest tests/
```

## Phase status

- **Phase 1** (this commit): restructure + voice + NN-fallback classifier ✅
- **Phase 2** (pending teammate): swap to multi-label classifier when `label2id.json` + tokenizer files arrive. Lands `MultilabelClassifier` behind the same factory.
- **Phase 3** (later): multi-intent dispatch, TSS bidirectional commands for `set_*` PR intents, GEMINI-move prep.
