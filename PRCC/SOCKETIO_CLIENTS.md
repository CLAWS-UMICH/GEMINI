# Socket.IO 

This backend runs **Flask-SocketIO** on **TCP port 5001**, bound to **all interfaces** (`0.0.0.0`). 

## Connect

**URL:** `http://<BACKEND_HOST_IP>:5001`

### Example

```python
import socketio
import threading
import time
from flask_socketio import SocketIO, emit

sio = socketio.Client()
is_running = True

@sio.event
def connect():
    print("connected", sio.sid)

@sio.event
def disconnect():
    print("disconnected")

@sio.on("rover-telemetry")
def on_rover(data):
    print("rover ok")

@sio.on("ltv-telemetry")
def on_ltv(data):
    print("ltv ok")

sio.connect("http://127.0.0.1:5001")
try:
    sio.emit("rover-throttle", 100.0)
    print("emit ok")
except Exception as e:
    print(f"Error sending rover throttle: {e}")
sio.wait()
```

Note that the try: and except: aren't actually necessary, just nice to have. It can easily be:

```python
sio.emit("rover-throttle", 100.0) 
```

On its own. Or,

```python
if (case):
    sio.emit("rover-throttle", 100,0)
```

Register handlers with `@sio.on("<event_name>")` for each server event you care about.

---

## TSS rover / status controls (`udp_client.py`)


`set_brakes(engaged: bool)` | 1107

`set_throttle(value: float)` | 1109  

`set_steering(value: float)` | 1110  

`set_heating(value: float)` | 1103  

`set_cooling(value: float)` | 1104  

`set_headlights(value: float)` | 1106  

`send_ping(value=1.0)` | 2050  

`send_debug_ping(value=1.0)` | 2051  


Telemetry pulls (used by the server loop, not typical client emits): `fetch_rover_json` (0), `fetch_eva_json` (1), `fetch_ltv_json` (2), `fetch_ltv_errors_json` (3).

Read **NASA’s TSS** docs for full JSON field meanings

---

## From server to you <3

`rover-telemetry` | JSON object + `local_timestamp` (ISO)  

`ltv-telemetry` | JSON object + `local_timestamp`  

`ltv-errors-telemetry` | JSON object + `local_timestamp`  

`eva-telemetry` | JSON object + `local_timestamp`  

`matrix-sync` | 2D JSON array (nested lists); navigation / display matrix  

`error` | `{"error": str, "local_timestamp": str}`  

`matrix-sync` is the 2D matrix for navigation/display on the frontend 

---

## From you to server.

Use **`sio.emit(event, data)`**; payloads must be JSON or Python objects

`rover-throttle` | Single float  

`rover-steering` | Single float  

`rover-brakes` | Boolean  

`rover-heating` | Single float (0…1)  

`rover-cooling` | Single float (0…1)  

`rover-headlights` | Single float (0…1)  

`rover-ping` | Optional float  

`rover-debug-ping` | Optional float  

`matrix` | 2D array  

Examples:

```python
sio.emit("rover-throttle", 10.0)
sio.emit("rover-steering", -0.2)
sio.emit("rover-brakes", False)
sio.emit("rover-heating", 0.5)
sio.emit("rover-cooling", 0.0)
sio.emit("rover-headlights", 1.0)
sio.emit("rover-ping")
sio.emit("rover-debug-ping", 1.0)
sio.emit("matrix", [[0, 1], [2, 3]])
```
