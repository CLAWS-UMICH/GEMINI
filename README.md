# CORVUS Python Server

Voice → classify → telemetry-grounded response loop for the CLAWS-UMICH suit-and-rover stack. Two modes share one Python package:

- **`corvus-eva`** — Unity-paired. WebSocket server on `:8765`. Unity handles wake word, mic capture, and Piper TTS playback; Python handles Whisper STT, classification, and response text. EVA-side intents (vitals, menus, navigation, etc.) are classified by a fine-tuned multi-intent model in `models/EVA-Model/`.
- **`corvus-pr`** — standalone. Full audio loop in Python: openWakeWord → Silero VAD → Whisper STT → classify → Piper TTS. PR-side intents are classified by a multi-label model in `models/PR-Model/`.

Both modes share the same telemetry source ([stilettocode/TTTDTT](https://github.com/stilettocode/TTTDTT) on `:5001`, which mirrors NASA TSS over UDP) and the same dispatcher.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- A running [TTTDTT](https://github.com/stilettocode/TTTDTT) instance reachable at `$TTTDTT_URL` (defaults to `http://localhost:5001`). Without it, handlers respond "Telemetry unavailable right now."
- For `corvus-pr` voice mode: working mic + speaker, plus the PortAudio shared library:
  - **Linux/WSL:** `sudo apt install libportaudio2`
  - **Windows:** PortAudio ships with `sounddevice`; nothing extra to install.
- Optional: a CUDA GPU. STT moves to GPU automatically; everything else stays on CPU by design.

## Setup

From the project root:

```bash
uv sync                          # installs all Python deps into .venv
./scripts/install_whisper.sh     # downloads Whisper medium.en (~480 MB)
./scripts/install_piper.sh       # downloads Piper en_US-lessac-medium (~60 MB)
./scripts/install_wakeword.sh    # verifies in-repo wake-word ONNX files
```

What you get out of the box (already in the repo):

| Asset                                    | Used by                          |
|------------------------------------------|----------------------------------|
| `models/EVA-Model/`                      | EVA-mode classifier (MultiIntent)|
| `models/PR-Model/`                       | PR-mode classifier (Multilabel)  |
| `models/classifier/minilm-nn/`           | NN-classifier fallback           |
| `models/embeddings/minilm/`              | Encoder for the NN fallback      |
| `models/intent_catalogs/`                | Per-mode intent label masks      |
| `models/wake_word/hey_corvus.onnx`       | Custom "hey corvus" trigger (PR) |
| `models/openwakeword/*.onnx`             | Wake-word preprocessor (PR)      |

After install, the only additional artifacts on disk are `models/stt/whisper-medium.en/model.bin` and `models/tts/piper/en_US-lessac-medium.onnx[.json]`.

### Windows note: Microsoft Defender

Defender can quarantine `.onnx` / `.pyd` files inside `.venv\Lib\site-packages\` after `uv sync`. If you see `NoSuchFile: melspectrogram.onnx failed` or `ModuleNotFoundError: dotenv`, that's the cause. Add a folder exclusion:

```powershell
Add-MpPreference -ExclusionPath "C:\path\to\CORVUS_Voice_Server"
```

(elevated PowerShell), then re-run `uv sync --reinstall`. The wake-word preprocessor is now bundled at `models/openwakeword/` outside the venv to dodge this entirely.

## Run

### EVA mode — `uv run corvus-eva`

Unity-paired. Python boots a WebSocket server on `0.0.0.0:8765`, connects to TTTDTT as a Socket.IO client, loads the classifier, and loads Whisper STT (mandatory).

Whisper checkpoint MUST be installed first — startup exits with `FileNotFoundError` if `models/stt/whisper-medium.en/` is missing.

Expected boot logs:
```
EVA mode: EVA-Model bundle present at .../models/EVA-Model; building MultiIntentClassifier
[SUCCESS] Classifier loaded (MultiIntentClassifier)
Loading Whisper from .../whisper-medium.en (device=cuda|cpu, compute_type=float16|int8)
[SUCCESS] Whisper STT loaded
[SUCCESS] Silero VAD loaded
websockets.server: server listening on 0.0.0.0:8765
[SUCCESS] Server running on ws://0.0.0.0:8765
[INFO] Waiting for Unity connection...
```

#### Wire protocol with Unity

Unity opens one WebSocket and keeps it open for the session. Text frames carry JSON control messages; binary frames carry raw int16 LE PCM @ 16 kHz mono, ~3200 bytes per ~100 ms chunk.

Unity → Python — start utterance:
```json
{"type": "start", "sample_rate": 16000, "channels": 1}
```

Unity → Python — audio chunks (binary): raw int16 little-endian, no header.

Unity → Python — cancel:
```json
{"type": "stop"}
```

Python → Unity — terminal response:
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

`response` is always present (may be `""` on STT failure to keep Unity unstuck). The other fields are optional. Python emits `final` after Silero VAD detects end-of-speech (default 700 ms silence; `EVA_VAD_HANGOVER_MS`). A 30 s hard cap (`EVA_MAX_UTTERANCE_S`) forces finalize if VAD never fires.

#### Ad-hoc EVA smoke test (no Unity)

```bash
EVA_E2E=1 uv run python -m pytest tests/test_eva_handler_e2e.py -v
```

Or drive the state machine directly with synthetic PCM via `tests/test_eva_protocol.py` and `tests/test_eva_session.py`.

### PR mode — two flavors

PR mode is standalone — no WebSocket, no Unity.

| Command                     | Mic | Speaker | Use case                                  |
|-----------------------------|-----|---------|-------------------------------------------|
| `uv run corvus-pr`          | ✓   | ✓       | Full voice loop. The demo path.           |
| `uv run corvus-pr --text`   |     | ✓       | Type commands; Piper speaks responses. Useful for rapid classifier testing without a mic. |

Voice-mode requirements:
- All install scripts run
- PortAudio + working mic and speaker (`uv run python -c "import sounddevice; print(sounddevice.query_devices())"` should list at least one input and output device)
- TTTDTT reachable (otherwise responses say "Telemetry unavailable")

Expected boot logs (voice mode):
```
[INFO] Starting CORVUS-PR Agent…
[INFO] Mode: voice
[INFO] TTTDTT client started (target: http://localhost:5001)
PR mode: PR-Model sidecars present at .../models/PR-Model; building MultilabelClassifier
[SUCCESS] Classifier loaded (MultilabelClassifier)
[SUCCESS] Piper TTS loaded
[SUCCESS] Whisper STT loaded
[SUCCESS] Silero VAD loaded
[SUCCESS] openWakeWord loaded
[INFO] Wake word listener active. Say 'hey corvus' to interact.
```

After a wake-word hit:
```
[SUCCESS] Wake word detected.
[INFO] Listening (VAD-gated)…
[INFO] Heard: 'what is my speed'
[INFO] [get_speed @ 0.99] Current rover speed is 1.42 meters per second.
```

## Mode flows

### EVA mode

```
Unity ──WS text─▶ {type: "start", sample_rate: 16000, channels: 1}
Unity ──WS bin──▶ raw int16 LE PCM chunks (≈100 ms each)
                    ↓
               Silero VAD (32 ms frames, 700 ms hangover) ──▶ end-of-speech
                    ↓
               Whisper STT ──▶ transcript
                    ↓
               MultiIntentClassifier(transcript)
                    ↓
               dispatch → response
                    ↓
Python ──WS text─▶ {type: "final", response, transcript?, intent?, confidence?, parameters?, latency_ms?}
                    ↓
                  Unity ──▶ Piper TTS
```

### PR mode

```
idle
  ↓
openWakeWord triggers ("hey corvus")
  ↓
shared input stream feeds Silero VAD-gated capture
  ↓
Whisper STT ──▶ text
  ↓
MultilabelClassifier(text)
  ↓
dispatch → response_text ──▶ Piper TTS ──▶ speaker
  ↓
back to idle
```

## Device routing (CPU vs GPU)

Single decision point in `src/voice/devices.py::select_stt_device()`. Logged at boot.

| Component         | GPU path                            | CPU path                           |
|-------------------|-------------------------------------|------------------------------------|
| Whisper `medium.en` | `device=cuda, compute_type=float16` | `device=cpu, compute_type=int8`    |
| Classifier        | CPU                                 | CPU                                |
| Piper TTS         | CPU                                 | CPU                                |
| Silero VAD        | CPU                                 | CPU                                |
| openWakeWord      | CPU                                 | CPU                                |

End-to-end latency (end-of-speech → start-of-response audio):

| Path                       | Latency       |
|----------------------------|---------------|
| GPU `float16`, medium.en   | ~600–900 ms   |
| CPU `int8`, medium.en      | ~1.5–3 s      |

medium.en is heavier than base.en; if you need lower latency on CPU and can accept lower accuracy, point `src/voice/stt.py::DEFAULT_MODEL_DIR` at `whisper-base.en` and re-run `install_whisper.sh` with `base.en`.

To force CPU fallback locally for testing: `CUDA_VISIBLE_DEVICES="" uv run corvus-pr`.

## Environment variables

| Variable                | Default                | Description                                                  |
|-------------------------|------------------------|--------------------------------------------------------------|
| `TTTDTT_URL`            | `http://localhost:5001`| TTTDTT Socket.IO endpoint                                    |
| `STALE_TELEMETRY_S`     | `10.0`                 | Seconds before cached telemetry is considered stale          |
| `EMIT_VOICESTRING`      | `1`                    | Re-publish the final `response` text on TTTDTT `voiceString` |
| `EVA_VAD_HANGOVER_MS`   | `700`                  | Silence (ms) after speech before EVA emits `{type:"final"}`  |
| `EVA_MAX_UTTERANCE_S`   | `30`                   | Hard cap on a single utterance before forced finalize        |
| `WS_HOST`               | `0.0.0.0`              | EVA WebSocket bind host                                      |
| `WS_PORT`               | `8765`                 | EVA WebSocket bind port                                      |

## Tests

```bash
uv run python -m pytest tests/
```

Tests run offline. The integration-style tests that need the real model bundles auto-skip if those bundles aren't present.

## Adding a new intent

1. Add a handler in `src/core/responder/handlers_eva.py` or `handlers_pr.py` (depending on which mode owns it). Signature: `handle_x(command, cache, classification) -> str`.
2. Register the label → handler in `registry_eva.py` or `registry_pr.py`.

If you also need to teach the classifier the new label, add it to the training data and retrain (see the training notebook under `scripts/`).

## Project layout

```
src/
  config.py                  ── Env-driven settings + paths
  core/
    classifier/              ── factory.py + Multilabel + MultiIntent + NN fallback
    responder/               ── handler registries, dispatch, templates
    telemetry/               ── TTTDTT Socket.IO client + TTL cache
  voice/
    audio_io.py              ── sounddevice mic/speaker (PR only)
    devices.py               ── single GPU/CPU decision
    stt.py                   ── faster-whisper wrapper
    tts.py                   ── Piper wrapper
    vad.py                   ── Silero VAD
    wake_word.py             ── openWakeWord (uses bundled preprocessors)
  modes/
    eva/main.py              ── EVA WS server entry
    eva/websocket_handler.py ── per-connection state machine
    pr/main.py               ── PR voice-loop entry
models/                      ── checkpoints, tokenizers, sidecars (see Setup)
scripts/                     ── install_*.sh helpers
tests/                       ── pytest suite
```
