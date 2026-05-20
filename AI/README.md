# GEMINI AI Controller System

## Overview

The GEMINI AI Controller is an autonomous rover control system designed for lunar exploration missions. It communicates with the Pressurized Rover Control Center (PRCC) to manage rover navigation, resource monitoring, and LTV (Lunar Terrain Vehicle) search operations.

**Key Components:**
- **AI Controller** (`AI_controller.py`) - Main navigation and decision-making system
- **Predictive Warning System** (`predictive_warning_system.py`) - Real-time resource monitoring and failure prediction
- **Socket.IO Integration** - Event-driven communication with backend services

---

## Architecture

### System Flow

```
dumbdrive / AI Controller
    ↕ Socket.IO rover-* commands + telemetry
TTTDTT backend
    ↕ UDP command packets + JSON telemetry
TSS
    ↔ DUST simulator
```

`dumbdrive.py` now uses the backend Socket.IO route by default. The backend is
the only process that needs the TSS UDP address during normal operation.

### Core Classes

#### PRController
Main rover control system with 5 operational phases:

1. **Connect to Infrastructure** - Establish link with TSS and simulation
2. **Generate Path to LKP** - Plan route to LTV's last known position
3. **Process Warnings** - Monitor resources and predict failures
4. **Navigate to LKP** - Execute waypoint-following with obstacle avoidance
5. **Search for LTV** - Perform signal-based search operations

---

## Features

### 1. Predictive Warning System

The system uses two complementary warning subsystems:

#### Subsystem 1: Rate-of-Change Tracker
- **Function**: Predicts when resources will hit critical thresholds
- **Method**: Linear least-squares regression on historical data
- **Trigger**: When projected breach occurs within 10 timesteps (configurable)
- **Warning Type**: `PREDICTIVE`

**Tracked Resources:**
- `battery_level` - Critical at 30%
- `oxygen_tank` - Critical at 25%
- `oxygen_pressure` - Critical at 2997 psi
- `coolant_storage` - Critical at 80%

#### Subsystem 2: Instantaneous Threshold Monitor
- **Function**: Detects immediate threshold violations
- **Method**: Direct comparison against safe operating ranges
- **Trigger**: On every telemetry update
- **Warning Type**: `WARNING`

**Monitored Parameters:**
- Driving (pitch, roll, speed, throttle, steering, surface_incline)
- Navigation (distance_from_base)
- Oxygen system (tank level, pressure)
- Thermal (fan RPMs)
- Cabin environment (pressure, temperature)
- Coolant system (pressure, storage)
- Power (battery level)

### 2. Path-Aware Warning Filtering

Warnings are intelligently filtered based on current navigation state:
- **Predictive warnings** only trigger if resource failure occurs before path completion
- Path completion time is estimated based on:
  - Remaining waypoint distances
  - Estimated rover speed
  - Current position
- Prevents false alarms for non-critical issues during short missions

### 3. Navigation System

#### Path Generation
- Generates straight-line paths to LKP (replaceable with A* pathfinding)
- Path visualization emitted to frontend for monitoring

#### Navigation Loop
- Waypoint following with control outputs (throttle, steering, brakes)
- Obstacle detection with path replanning
- Warning checks at each waypoint
- Configurable timestep intervals (default: 0.2s)

#### Obstacle Avoidance
- Mock LIDAR detection (probabilistic in simulation)
- Triggers path recalculation
- Re-evaluates warnings after replanning

### 4. LTV Search System

- **Strategy**: Signal-based directional search
- **Tool**: Rover ping with signal strength monitoring
- **Budget**: Limited ping attempts (default: 10)
- **Success Criteria**: Signal strength > -5.0 dB (tunable)
- **Movement**: Direction-biased random walk toward stronger signals

---

## Usage

### Basic Setup

```python
from AI_controller import PRController

# Initialize controller
controller = PRController()

# Setup telemetry (from TSS)
tss_json = {
    "pr_telemetry": {
        "battery_level": 95,
        "oxygen_tank": 98,
        # ... other telemetry fields
    }
}

# Process warnings before navigation
warnings = controller.process_warnings(tss_json)
if warnings:
    for w in warnings:
        print(f"[{w['severity']}] {w['message']}")

# Navigate to LKP
controller.navigate_to_lkp(tss_json)
```

### Warning Processing

```python
# Full telemetry dict with pr_telemetry key
telemetry = {
    "pr_telemetry": {...}
}

# Get warnings (automatically filters by path completion time)
warnings = controller.process_warnings(telemetry)

# Or with explicit path time estimate
warnings = controller.process_warnings(telemetry, estimated_path_time=50)
```

### Warning Structure

Each warning dict contains:
```python
{
    "valuename": str,        # Field name (e.g., "battery_level")
    "value": float,          # Current sensor reading
    "severity": str,         # "WARNING" or "PREDICTIVE"
    "breach": str,           # "LOW", "HIGH", or "PROJECTED"
    "threshold": float,      # Critical threshold value
    "unit": str,             # Unit of measurement
    "message": str,          # Human-readable message
    "notes": str             # Safety documentation
}
```

---

## Configuration

### Environment Variables

```bash
# dumbdrive.py
DUMBDRIVE_TRANSPORT=socket
DUMBDRIVE_BACKEND_URL=http://127.0.0.1:5001
DUMBDRIVE_TSS_HOST=192.168.4.231       # only used when DUMBDRIVE_TRANSPORT=udp
DUMBDRIVE_TSS_PORT=14141               # only used when DUMBDRIVE_TRANSPORT=udp

# predictive_warning_system.py
PROXY_URL=http://172.27.175.241:5001    # Socket.IO proxy address
EARLY_WARNING_TIMESTEPS=10              # Early warning window
```

### Telemetry Ranges

Critical thresholds defined in `THRESHOLDS` dict:
```python
"battery_level": {
    "low": 30,       # Minimum safe level (%)
    "high": 100,
    "unit": "%",
    "notes": "Battery level below minimum of 30%."
}
```

---

## Testing & Development

### Test Files

| File | Purpose |
|------|---------|
| `test_warnings.py` | Inject fake telemetry to test warning system |
| `test_integration.py` | Validate `processTelemetry` function |
| `test_integration_ai_controller.py` | Integration tests with controller |

### Running Tests

```bash
# Test predictive warning system
python test_integration.py

# Test AI controller integration
python test_integration_ai_controller.py
```

### Dumbdrive backend route

Run the full `dumbdrive -> backend -> TSS` stack in three terminals:

```bash
cd TSS2026
./run.sh
```

```bash
cd TTTDTT/backend
TSS_UDP_HOST=<tss-ip> python app.py
```

```bash
cd GEMINI-2/AI/controlfiles
DUMBDRIVE_BACKEND_URL=http://<backend-ip>:5001 python dumbdrive.py
```

For direct UDP fallback during local debugging:

```bash
cd GEMINI-2/AI/controlfiles
DUMBDRIVE_TRANSPORT=udp DUMBDRIVE_TSS_HOST=<tss-ip> python dumbdrive.py
```

### Monkey-Patching for Development

For local testing without real hardware:

1. Use `monkey_patchified_version_of_ians_backend.py` to inject fake TSS data
2. Replace `app.py` in Ian's backend folder
3. Run all 3 services: TSS, Ian's backend, and this AI controller
4. Use `test_warnings.py` to simulate telemetry events

---

## Socket.IO Events

See https://github.com/stilettocode/TTTDTT/blob/master/SOCKETIO_CLIENTS.md for the socket interface

---

## Outstanding Issues & Future Work

### TODO Items

- [ ] Integrate Sam's pathfinding algorithm
- [ ] Add rover response commands based on warning severity (auto-throttle reduction, emergency brake)
- [ ] Implement non-linear resource prediction models
- [ ] Add safety critical action triggers (e.g., emergency return-to-base)

### Endpoint Configuration

Update the Socket.IO connection URL in `AI_controller.py` main script:
```python
# Change this to point to the PRCC's backend service
sio.connect("http://35.2.123.225:5001")
```

---

## Performance Characteristics

- **Telemetry Processing**: ~10ms per update
- **Warning Detection**: <5ms (threshold checks), ~20ms (predictive analysis)
- **Path Calculation**: ~5ms per recalculation
- **Memory Usage**: ~1-2MB for 1000 telemetry history points

---

## Safety Notes

- Predictive warnings assume constant rate-of-change (may be inaccurate during dynamic maneuvers)
- Early warning window (10 timesteps) is conservative but tunable
- Always verify system response during real-world testing
- Critical thresholds are based on NASA EVA specifications and rover documentation
