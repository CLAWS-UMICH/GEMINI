# CORVUS Python Server — Claude Context

## Architecture

The server is a voice-command→telemetry-response loop for the CORVUS rover challenge. Full design is in `docs/superpowers/specs/2026-05-11-corvus-rover-pivot-design.md`. At startup (`src/server/main.py`) the process builds a `TelemetryCache`, a Socket.IO client to TTTDTT, and an `IntentClassifier`, then starts the WebSocket server. Incoming Unity commands hit `src/server/websocket_handler.py`, which calls `dispatch.respond()` and returns a JSON object with a `response_text` field. Optionally a `voiceString` Socket.IO event is emitted if `EMIT_VOICESTRING=1`.

## Key Seams

| File | Role |
|---|---|
| `src/responder/registry.py` | Single dict: intent label → handler function |
| `src/responder/dispatch.py` | Confidence gate + registry lookup (~6 lines) |
| `src/responder/handlers.py` | Per-intent response functions (currently 6 representative handlers) |
| `src/responder/fallback.py` | `LOW_CONFIDENCE_REPLY`, `UNKNOWN_INTENT_REPLY`, `TELEMETRY_UNAVAILABLE_REPLY` |
| `src/telemetry/cache.py` | `TelemetryCache`: TTL-based snapshot store, thread-safe via `Lock` |
| `src/telemetry/client.py` | Socket.IO client to TTTDTT; four event handlers write to `cache.put` |
| `src/classifier/classifier_protocol.py` | `ClassifierProtocol` — the swap point for any replacement model |
| `src/classifier/intent_classifier.py` | Current model: MiniLM + 2-layer NN, ~97% val accuracy on 87-intent set |

## How to Add a New Intent

1. Write a handler function in `src/responder/handlers.py`:
   ```python
   def handle_battery_voltage(cache: TelemetryCache) -> str:
       snap = cache.get()
       if snap is None:
           return TELEMETRY_UNAVAILABLE_REPLY
       return f"Battery voltage is {snap.batt_voltage:.1f} V."
   ```
2. Register it in `src/responder/registry.py`:
   ```python
   "battery_voltage": handle_battery_voltage,
   ```
   Done. No other files need to change.

## Classifier Note

Intent labels in `training_data.json` are scaffolding for the current MiniLM model. A teammate's replacement model (different architecture, different training pipeline) can slot in behind the same `ClassifierProtocol` interface without touching the responder layer. The protocol requires a single method: `classify(text: str) -> ClassifierResult`.
