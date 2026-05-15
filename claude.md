# CORVUS Python Server — Claude Context

## Architecture

Two-mode voice agent sharing a single Python package. Full spec (gitignored):
`docs/superpowers/specs/2026-05-14-corvus-dual-mode-voice-and-model-swap-design.md`.

| Mode            | Entry point         | Audio I/O              | TTS owner        |
|-----------------|---------------------|------------------------|------------------|
| EVA             | `uv run corvus-eva` | Unity over WS :8765    | Unity (Piper)    |
| PR (standalone) | `uv run corvus-pr`  | Python (sounddevice)   | Python (Piper)   |

Both modes share `src/core/` (classifier, telemetry cache + TTTDTT SIO client,
responder dispatch). Mode-specific code lives under `src/modes/eva/` and
`src/modes/pr/`. Voice stack lives in `src/voice/`.

## Key seams

| File | Role |
|---|---|
| `src/core/classifier/factory.py` | Selects classifier impl (NN fallback ↔ Multilabel) |
| `src/core/classifier/classifier_protocol.py` | The swap point for any replacement model |
| `src/core/classifier/nn_classifier.py` | Legacy MiniLM + 2-layer NN (Phase 1 default) |
| `src/core/responder/registry_eva.py` | `{eva_intent: handler}` |
| `src/core/responder/registry_pr.py` | `{pr_intent: handler}` (17 handlers) |
| `src/core/responder/dispatch.py` | Confidence gate + registry lookup (takes registry as arg) |
| `src/core/telemetry/cache.py` | TTL-keyed snapshot store |
| `src/core/telemetry/client.py` | Socket.IO client to TTTDTT |
| `src/voice/devices.py` | Single GPU/CPU decision for STT |
| `src/voice/stt.py` | faster-whisper wrapper |
| `src/voice/tts.py` | Piper wrapper (PR only) |
| `src/voice/wake_word.py` | openWakeWord (PR only) |
| `src/voice/vad.py` | Silero VAD (PR only) |
| `src/voice/audio_io.py` | sounddevice mic capture + playback |
| `src/modes/eva/main.py` | EVA entry: classifier factory + WS server |
| `src/modes/eva/websocket_handler.py` | Accepts `{command}` or `{audio}` payloads |
| `src/modes/pr/main.py` | PR entry: full voice loop, `--stdin` + `--speak` debug modes |

## Device routing

`src/voice/devices.py::select_stt_device()` is the single decision point:
- **GPU available:** `(cuda, float16)` for Whisper
- **No GPU:** `(cpu, int8)` for Whisper

Classifier, TTS, VAD, wake-word stay on CPU by design. See spec §5.

End-to-end latency targets: ~400–500 ms on GPU, ~700 ms–1.2 s on CPU.

## How to add a new intent

1. Write a handler in `src/core/responder/handlers_eva.py` or `handlers_pr.py`
   (depending on which mode owns it). Signature: `handle_x(command, cache, classification) -> str`.
2. Register the label → handler in `registry_eva.py` or `registry_pr.py`.
   Done.

## Classifier note

Phase 1 uses the legacy MiniLM + 2-layer NN classifier (87 labels). When the
teammate's multi-label sidecars arrive (`label2id.json` + tokenizer files
under `models/multilabel/`), the factory automatically picks
`MultilabelClassifier` on next boot.

## Third-party API notes

- **openwakeword pinned to >=0.4.0** (not >=0.6.0): 0.6.0 hard-requires
  tflite-runtime which has no Python 3.13 wheels. 0.4.0 ships pretrained
  ONNX models bundled with the package; `WakeWordDetector` resolves friendly
  names like `'hey_jarvis'` against `openwakeword.get_pretrained_model_paths()`.
- **torchaudio pinned to >=2.9.0,<2.10** to match torch 2.9.x — silero-vad
  otherwise pulled torchaudio 2.11 with a binary that wouldn't load against
  torch 2.9.
- **Piper 1.4.x** uses `voice.synthesize(text) -> Iterable[AudioChunk]` with
  `chunk.audio_int16_array`. The older `synthesize_stream_raw` API doesn't
  exist in this version.
- **sounddevice** requires `libportaudio2` at the system level. The PR-mode
  audio path can't import without it; EVA mode and PR `--stdin` are unaffected.
