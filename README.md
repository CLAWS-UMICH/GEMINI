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

```bash
# EVA mode (Unity-paired):
uv run corvus-eva

# PR mode (standalone, voice):
uv run corvus-pr

# PR mode (stdin, useful for debug):
uv run corvus-pr --stdin

# PR mode (stdin + speak responses):
uv run corvus-pr --stdin --speak
```

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
