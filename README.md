# CORVUS Python Server

Voice → classify → telemetry-grounded response loop for the CORVUS rover challenge. Unity sends a transcribed command over WebSocket; the server classifies intent, reads a live telemetry snapshot from TTTDTT, and returns a plain-text response Unity can speak.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- A running [TTTDTT](https://github.com/Lunar-Minecraft-Society/TTTDTT) instance reachable at `$TTTDTT_URL`

## Setup

```bash
uv sync
uv run corvus
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TTTDTT_URL` | `http://localhost:5001` | Socket.IO endpoint of the TTTDTT telemetry server |
| `STALE_TELEMETRY_S` | `30` | Seconds before a cached telemetry reading is considered stale |
| `EMIT_VOICESTRING` | `0` | Set to `1` to emit a `voiceString` Socket.IO event alongside the WS response |
| `WS_HOST` | `0.0.0.0` | WebSocket listen host |
| `WS_PORT` | `8765` | WebSocket listen port |

## Manual End-to-End Smoke Test

**Terminal 1 — start the server**

```bash
uv run corvus
```

**Terminal 2 — inject fake telemetry** (requires `python-socketio[asyncio_client]`)

```python
# emit_telemetry.py
import asyncio
import socketio

async def main():
    sio = socketio.AsyncClient()
    await sio.connect("http://localhost:5001")
    await sio.emit("eva-telemetry", {"heart_bpm": 78, "batt_time_left": 42})
    print("emitted eva-telemetry")
    await sio.disconnect()

asyncio.run(main())
```

```bash
python emit_telemetry.py
```

**Terminal 3 — send a command and check the response**

```bash
# using wscat
wscat -c ws://localhost:8765 -x '{"command": "what is my heart rate"}'
```

Expected response shape:

```json
{
  "status": "success",
  "intent": "vitals_heart_rate",
  "confidence": 0.95,
  "response_text": "Your heart rate is 78 bpm."
}
```

## Tests

```bash
uv run pytest tests/
```
