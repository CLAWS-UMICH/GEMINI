"""
Predictive Warning System — Pressurized Rover
==============================================
Reads live telemetry via the Socket.IO proxy service and runs two warning
sub-systems:

  SUB-SYSTEM 1 · Rate-of-Change Tracker
      Records telemetry values over time, fits a linear model (least-squares),
      and predicts how many timesteps remain until a critical threshold is hit.

      recordRateOfChange(valuename, value, timestep)
      howLongUntilValue(valuename, target)   → float | None  (timesteps remaining)
      getSlope(valuename)                    → float | None
      predictValueAtTimestep(valuename, t)   → float | None

  SUB-SYSTEM 2 · Instantaneous Threshold Monitor
      Checks each incoming reading against a defined safe range and fires a
      warning immediately when a value leaves that range.

      checkThreshold(valuename, value)       → warning dict | None
      checkAllThresholds(readings)           → list[warning dict]

  Socket.IO integration:
      Connects to the proxy service and reacts to "rover-telemetry" events,
      calling processTelemetry() for each update instead of HTTP polling.

      processTelemetry(telemetry, timestep)  → list[warning dict]
          Pass the full telemetry dict from the rover-telemetry event. Records
          every tracked field in Sub-system 1 and checks all thresholds in
          Sub-system 2.

  Configuration:
      PROXY_URL              — Socket.IO proxy service address (default: localhost:5001)
      EARLY_WARNING_TIMESTEPS — how soon a projected breach triggers a warning
      RATE_FIELDS            — which fields to track with Sub-system 1
"""

import socketio
from collections import defaultdict
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — edit these to match your environment
# ─────────────────────────────────────────────────────────────────────────────

PROXY_URL = "http://172.27.175.241:5001"   # Socket.IO proxy service address

# Fields to track with Sub-system 1 (rate-of-change), mapped to the critical
# target value that triggers a predictive warning. Field names match the TSS
# pr_telemetry keys from ROVER.json.
RATE_FIELDS: dict[str, float] = {
    # Source: rover-telemetry-ranges.pdf
    "battery_level":    30,     # warn when projected to hit the 30 % minimum
    "oxygen_tank":      25,     # warn when projected to hit the 25 % minimum
    "oxygen_pressure":  2997,   # warn when projected to drop below 2997 psi minimum
    "coolant_storage":  80,     # warn when projected to drop below 80 % minimum
}

# How many timesteps ahead counts as "soon enough to warn"
EARLY_WARNING_TIMESTEPS = 10


# ─────────────────────────────────────────────────────────────────────────────
# SUB-SYSTEM 1 — Rate-of-Change Tracker
# ─────────────────────────────────────────────────────────────────────────────

# Internal storage: { valuename: [(timestep, value), ...] }
_history: dict[str, list[tuple[float, float]]] = defaultdict(list)


def recordRateOfChange(valuename: str, value: float, timestep: float) -> None:
    """
    Record one telemetry reading for a named metric.

    Parameters
    ----------
    valuename : str   — TSS field name, e.g. "battery_level"
    value     : float — the sensor reading
    timestep  : float — mission_elapsed_time or poll counter

    Note: call processTelemetry() to record all tracked fields at once from
    a live telemetry event. Only call this directly for isolated testing.
    """
    _history[valuename].append((float(timestep), float(value)))


def getSlope(valuename: str) -> float | None:
    """
    Return the linear slope (delta_value / delta_timestep) for the named metric.
    Uses ordinary least-squares regression across all recorded points.
    Returns None if fewer than 2 data points are available.
    """
    points = _history.get(valuename, [])
    if len(points) < 2:
        return None
    t = np.array([p[0] for p in points], dtype=float)
    v = np.array([p[1] for p in points], dtype=float)
    slope, _ = np.polyfit(t, v, 1)
    return float(slope)


def howLongUntilValue(valuename: str, target: float) -> float | None:
    """
    Predict how many timesteps from the most recent recording until the
    metric reaches `target`.

    Formula:  dt = (target - current_value) / slope

    Returns
    -------
    float  — timesteps remaining
             positive = target is in the future (value is heading toward it)
             negative = target is in the past (value already passed it)
    None   — not enough data yet, or slope is zero (metric is stable)
    """
    points = _history.get(valuename, [])
    if len(points) < 2:
        return None

    slope = getSlope(valuename)
    if slope is None or abs(slope) < 1e-12:
        return None  # stable — no meaningful prediction

    _, current_value = points[-1]
    dt = (target - current_value) / slope
    return float(dt)


def predictValueAtTimestep(valuename: str, future_timestep: float) -> float | None:
    """
    Predict the value of a metric at a specific future timestep using the
    linear model fitted to all recorded data points.
    """
    points = _history.get(valuename, [])
    if len(points) < 2:
        return None
    t = np.array([p[0] for p in points], dtype=float)
    v = np.array([p[1] for p in points], dtype=float)
    slope, intercept = np.polyfit(t, v, 1)
    return float(slope * future_timestep + intercept)


def clearHistory(valuename: str | None = None) -> None:
    """Clear stored history for one metric, or all metrics if valuename is None."""
    if valuename is None:
        _history.clear()
    else:
        _history.pop(valuename, None)


def getHistory(valuename: str) -> list[tuple[float, float]]:
    """Return the full recorded history as [(timestep, value), ...]."""
    return list(_history.get(valuename, []))


# ─────────────────────────────────────────────────────────────────────────────
# SUB-SYSTEM 2 — Instantaneous Threshold Monitor
# ─────────────────────────────────────────────────────────────────────────────
#
# Sources: TSS pr_telemetry field names (ROVER.json), NASA EVA safety docs,
#          aerospace cabin environment specifications.
#
# Format per entry:
#   "field_name": {
#       "low":   float | None,   # minimum safe value  (None = no lower bound)
#       "high":  float | None,   # maximum safe value  (None = no upper bound)
#       "unit":  str,
#       "notes": str,
#   }

THRESHOLDS: dict[str, dict] = {
    # All ranges from: rover-telemetry-ranges.pdf
    # Format: low = min from PDF, high = max from PDF
    # nominal value noted in comments where specified

    # ── Driving / Motion ─────────────────────────────────────────────────────
    "pitch": {
        "low":   -50,
        "high":   50,
        "unit":  "deg",
        "notes": "Rover pitch outside safe range (-50 to 50 deg).",
    },
    "roll": {
        "low":   0,
        "high":  50,
        "unit":  "deg",
        "notes": "Rover roll outside safe range (0 to 50 deg).",
    },
    "speed": {
        "low":   0,
        "high":  18,    # m/s per telemetry ranges doc
        "unit":  "m/s",
        "notes": "Rover speed exceeds safe maximum of 18 m/s.",
    },
    "throttle": {
        "low":   0,
        "high":  100,
        "unit":  "%",
        "notes": "Throttle outside valid range (0–100 %).",
    },
    "steering": {
        "low":  -1,
        "high":  1,
        "unit":  "",
        "notes": "Steering value outside valid range (-1 to 1).",
    },
    "surface_incline": {
        "low":  -50,
        "high":  50,
        "unit":  "deg",
        "notes": "Surface incline outside safe range (-50 to 50 deg).",
    },

    # ── Navigation ───────────────────────────────────────────────────────────
    "distance_from_base": {
        "low":   0,
        "high":  2500,  # meters per telemetry ranges doc
        "unit":  "m",
        "notes": "Rover beyond maximum safe range from base (2500 m).",
    },

    # ── Oxygen ───────────────────────────────────────────────────────────────
    "oxygen_tank": {
        "low":   25,    # % min per telemetry ranges doc
        "high":  100,
        "unit":  "%",
        "notes": "O2 tank below 25 % minimum.",
    },
    "oxygen_pressure": {
        "low":   2997,  # psi min — nominal 2997–3000 psi per telemetry ranges doc
        "high":  3000,
        "unit":  "psi",
        "notes": "O2 pressure outside nominal range (2997–3000 psi).",
    },

    # ── Fans ─────────────────────────────────────────────────────────────────
    "fan_pri_rpm": {
        "low":   29999,  # rpm — nominal 29999–30005 per telemetry ranges doc
        "high":  30005,
        "unit":  "rpm",
        "notes": "Primary fan RPM outside nominal range (29999–30005 rpm).",
    },
    "fan_sec_rpm": {
        "low":   29999,  # rpm — both fans should run at same range
        "high":  30005,
        "unit":  "rpm",
        "notes": "Secondary fan RPM outside nominal range (29999–30005 rpm).",
    },

    # ── Cabin Atmosphere ─────────────────────────────────────────────────────
    "cabin_pressure": {
        "low":   3.5,   # psi min, nominal 4.0, max 4.10 per telemetry ranges doc
        "high":  4.10,
        "unit":  "psi",
        "notes": "Cabin pressure outside safe range (3.5–4.10 psi, nominal 4.0).",
    },
    "cabin_temperature": {
        "low":   10,    # °C min, nominal 21°C per telemetry ranges doc
        "high":  None,  # no max specified
        "unit":  "°C",
        "notes": "Cabin temperature below minimum of 10°C (nominal 21°C).",
    },

    # ── External Environment ─────────────────────────────────────────────────
    "external_temp": {
        "low":   None,  # no min/max specified in doc — informational only
        "high":  None,
        "unit":  "°C",
        "notes": "External temperature — no safe range defined, monitor for trends.",
    },

    # ── Coolant System ───────────────────────────────────────────────────────
    "coolant_pressure": {
        "low":   495,   # psi min, nominal 500, max 501 per telemetry ranges doc
        "high":  501,
        "unit":  "psi",
        "notes": "Coolant pressure outside safe range (495–501 psi, nominal 500).",
    },
    "coolant_storage": {
        "low":   80,    # % min, nominal and max 100% per telemetry ranges doc
        "high":  100,
        "unit":  "%",
        "notes": "Coolant storage below minimum of 80 %.",
    },

    # ── Power ────────────────────────────────────────────────────────────────
    "battery_level": {
        "low":   30,    # % min per telemetry ranges doc
        "high":  100,
        "unit":  "%",
        "notes": "Battery level below minimum of 30 %.",
    },
}


def checkThreshold(valuename: str, value: float) -> dict | None:
    """
    Check one instantaneous reading against its safe range.
    Returns a warning dict if out of bounds, or None if nominal.
    """
    spec = THRESHOLDS.get(valuename)
    if spec is None:
        return None

    low  = spec.get("low")
    high = spec.get("high")
    unit = spec.get("unit", "")

    if low is not None and value < low:
        return {
            "valuename": valuename,
            "value":     value,
            "severity":  "WARNING",
            "breach":    "LOW",
            "threshold": low,
            "unit":      unit,
            "message":   f"{valuename} = {value} {unit} is BELOW safe minimum of {low} {unit}.",
            "notes":     spec.get("notes", ""),
        }

    if high is not None and value > high:
        return {
            "valuename": valuename,
            "value":     value,
            "severity":  "WARNING",
            "breach":    "HIGH",
            "threshold": high,
            "unit":      unit,
            "message":   f"{valuename} = {value} {unit} EXCEEDS safe maximum of {high} {unit}.",
            "notes":     spec.get("notes", ""),
        }

    return None


def checkAllThresholds(readings: dict[str, float]) -> list[dict]:
    """
    Batch-check a full telemetry snapshot.

    Parameters
    ----------
    readings : dict — the telemetry object from the rover-telemetry event

    Returns a list of all triggered warnings. Empty list = all nominal.
    """
    warnings = []
    for name, val in readings.items():
        # Skip booleans (e.g. ac_heating, brakes) and non-numeric fields
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        w = checkThreshold(name, val)
        if w:
            warnings.append(w)
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Combined: process one full telemetry snapshot
# ─────────────────────────────────────────────────────────────────────────────

def processTelemetry(telemetry: dict, timestep: float) -> list[dict]:
    """
    Main entry point. Called for every rover-telemetry event received from
    the Socket.IO proxy service.

    Parameters
    ----------
    telemetry : dict  — the data payload from the rover-telemetry event
    timestep  : float — use mission_elapsed_time from telemetry, or an
                        auto-incremented event counter as a fallback

    What this does:
      1. Records all RATE_FIELDS values in Sub-system 1 history
      2. Runs Sub-system 2 instantaneous threshold check on the full snapshot
      3. For each RATE_FIELDS entry, if the projected timesteps-to-threshold is
         within EARLY_WARNING_TIMESTEPS, adds a PREDICTIVE warning

    Returns a combined list of all triggered warnings this timestep.
    """
    warnings = []

    # Sub-system 1: record history for rate-tracked fields
    for field in RATE_FIELDS:
        if field in telemetry and isinstance(telemetry[field], (int, float)) and not isinstance(telemetry[field], bool):
            recordRateOfChange(field, telemetry[field], timestep)

    # Sub-system 2: check all values against safe thresholds immediately
    warnings.extend(checkAllThresholds(telemetry))

    # Sub-system 1: generate predictive warnings for fields approaching their target
    for field, target in RATE_FIELDS.items():
        dt = howLongUntilValue(field, target)
        if dt is None:
            continue
        if 0 < dt <= EARLY_WARNING_TIMESTEPS:
            unit = THRESHOLDS.get(field, {}).get("unit", "")
            slope = getSlope(field)
            warnings.append({
                "valuename": field,
                "value":     telemetry.get(field),
                "severity":  "PREDICTIVE",
                "breach":    "PROJECTED",
                "threshold": target,
                "unit":      unit,
                "message":   (
                    f"{field} projected to reach {target} {unit} "
                    f"in ~{dt:.1f} timesteps "
                    f"(current rate: {slope:.4f} {unit}/timestep)."
                ),
                "notes": THRESHOLDS.get(field, {}).get("notes", ""),
            })

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Socket.IO client — event-driven replacement for the HTTP polling loop
# ─────────────────────────────────────────────────────────────────────────────

def runSocketLoop() -> None:
    """
    Connect to the Socket.IO proxy service and react to rover-telemetry events.
    Replaces the original HTTP polling loop. Press Ctrl+C to stop.
    """
    sio = socketio.Client()
    event_count = 0

    print(f"Predictive Warning System started")
    print(f"Connecting to proxy: {PROXY_URL}")
    print(f"Rate tracking: {list(RATE_FIELDS.keys())}")
    print("-" * 60)

    @sio.event
    def connect():
        print(f"[INFO] Connected to proxy service (sid={sio.sid})")

    @sio.event
    def disconnect():
        print("[INFO] Disconnected from proxy service.")

    @sio.on("error")
    def on_error(data):
        print(f"[ERROR] Proxy error: {data.get('error', data)}")

    @sio.on("rover-telemetry")
    def on_rover_telemetry(data: dict):
        nonlocal event_count

        # Prefer mission_elapsed_time from the payload as the timestep;
        # fall back to a local event counter if the field is absent.
        timestep = data.get("mission_elapsed_time", event_count)

        warnings = processTelemetry(data, timestep)

        if warnings:
            print(f"\n[t={timestep}]  {len(warnings)} warning(s):")
            for w in warnings:
                print(f"  [{w['severity']}] {w['message']}")
                if w.get("notes"):
                    print(f"           → {w['notes']}")
        else:
            print(f"[t={timestep}] All nominal.")

        # TODO: based on the warnings here send some command to Ian's code through the socket connections
        # # Example: if battery is critically low, cut throttle
        # if w["valuename"] == "battery_level" and w["breach"] == "LOW":
        #     sio.emit("rover-throttle", 0.0)

        # # Example: if speed is too high, apply brakes
        # if w["valuename"] == "speed" and w["breach"] == "HIGH":
        #     sio.emit("rover-brakes", True)

        event_count += 1

    try:
        sio.connect(PROXY_URL, transports=["polling", "websocket"], wait_timeout=10)
        sio.wait()
    except KeyboardInterrupt:
        print("\nWarning system stopped.")
    finally:
        sio.disconnect()


# ─────────────────────────────────────────────────────────────────────────────
# Debug / Test Mode
# ─────────────────────────────────────────────────────────────────────────────

def runDebugMode() -> None:
    """
    Interactive debug mode. Lets you manually feed in data points for any
    metric and immediately see:
      - whether the value triggers a threshold warning
      - the current slope (rate of change)
      - how many timesteps until the metric hits its critical target value

    Run with:  python predictive_warning_system.py --debug
    """
    import random

    print("=" * 60)
    print("  Predictive Warning System — DEBUG MODE")
    print("=" * 60)
    print("Commands:")
    print("  record  — enter a data point manually")
    print("  random  — generate a random data point for a metric")
    print("  predict — show time-to-target for a metric")
    print("  status  — show slope + full history for a metric")
    print("  check   — instantly check any value against thresholds")
    print("  quit    — exit")
    print("-" * 60)

    timestep_counter = 0

    while True:
        cmd = input("\nCommand: ").strip().lower()

        # ── record ────────────────────────────────────────────────────────────
        if cmd == "record":
            name = input("  Metric name (e.g. battery_level): ").strip()
            val_str = input("  Value: ").strip()
            ts_str  = input(f"  Timestep [default={timestep_counter}]: ").strip()
            try:
                value    = float(val_str)
                timestep = float(ts_str) if ts_str else float(timestep_counter)
            except ValueError:
                print("  [!] Invalid number — skipping.")
                continue

            recordRateOfChange(name, value, timestep)
            timestep_counter = int(timestep) + 1
            print(f"  Recorded: {name} = {value} at t={timestep}")

            # Threshold check
            w = checkThreshold(name, value)
            if w:
                print(f"  ⚠  THRESHOLD WARNING: {w['message']}")
                print(f"     → {w['notes']}")
            else:
                print(f"  ✓  {name} = {value} is within safe bounds.")

            # Prediction if we have enough data
            target = RATE_FIELDS.get(name)
            if target is not None:
                dt = howLongUntilValue(name, target)
                slope = getSlope(name)
                if dt is not None:
                    print(f"  📈 Slope: {slope:.4f}/timestep")
                    print(f"  ⏱  Predicted timesteps until {name} = {target}: {dt:.2f}")
                else:
                    print(f"  (Need at least 2 data points to predict — recorded {len(getHistory(name))} so far)")
            else:
                print(f"  ('{name}' is not in RATE_FIELDS — no time-to-target prediction)")

        # ── random ────────────────────────────────────────────────────────────
        elif cmd == "random":
            print("  Known metrics:", list(THRESHOLDS.keys()))
            name = input("  Metric name: ").strip()
            spec = THRESHOLDS.get(name)

            # Build a sensible random range
            if spec:
                lo = spec["low"]  if spec["low"]  is not None else 0
                hi = spec["high"] if spec["high"] is not None else 100
                # Make it occasionally out-of-range for interesting output
                lo_gen = lo * 0.7
                hi_gen = hi * 1.3 if hi > 0 else hi * 0.7
            else:
                lo_gen, hi_gen = 0, 100

            value    = round(random.uniform(lo_gen, hi_gen), 2)
            timestep = float(timestep_counter)
            recordRateOfChange(name, value, timestep)
            timestep_counter += 1
            print(f"  Generated: {name} = {value} at t={timestep}")

            w = checkThreshold(name, value)
            if w:
                print(f"  ⚠  THRESHOLD WARNING: {w['message']}")
                print(f"     → {w['notes']}")
            else:
                print(f"  ✓  {name} = {value} is within safe bounds.")

            target = RATE_FIELDS.get(name)
            if target is not None:
                dt = howLongUntilValue(name, target)
                slope = getSlope(name)
                if dt is not None:
                    print(f"  📈 Slope: {slope:.4f}/timestep")
                    print(f"  ⏱  Predicted timesteps until {name} = {target}: {dt:.2f}")
                else:
                    print(f"  (Need at least 2 data points — recorded {len(getHistory(name))} so far)")

        # ── predict ───────────────────────────────────────────────────────────
        elif cmd == "predict":
            name      = input("  Metric name: ").strip()
            tgt_str   = input(f"  Target value [default = RATE_FIELDS target]: ").strip()
            history   = getHistory(name)

            if len(history) < 2:
                print(f"  (Only {len(history)} point(s) recorded for '{name}' — need at least 2)")
                continue

            target = float(tgt_str) if tgt_str else RATE_FIELDS.get(name)
            if target is None:
                print(f"  ('{name}' has no default target — please enter a target value)")
                continue

            dt    = howLongUntilValue(name, target)
            slope = getSlope(name)
            _, current = history[-1]
            print(f"  Current value : {current}")
            print(f"  Slope         : {slope:.4f}/timestep")
            if dt is not None:
                print(f"  Timesteps until {name} = {target}: {dt:.2f}")
            else:
                print(f"  Slope is effectively zero — metric appears stable.")

        # ── status ────────────────────────────────────────────────────────────
        elif cmd == "status":
            name    = input("  Metric name: ").strip()
            history = getHistory(name)
            if not history:
                print(f"  No data recorded for '{name}' yet.")
                continue
            print(f"  History for '{name}' ({len(history)} point(s)):")
            for ts, val in history:
                print(f"    t={ts:<8}  value={val}")
            slope = getSlope(name)
            if slope is not None:
                print(f"  Slope: {slope:.4f}/timestep")

        # ── check ─────────────────────────────────────────────────────────────
        elif cmd == "check":
            name    = input("  Metric name: ").strip()
            val_str = input("  Value to check: ").strip()
            try:
                value = float(val_str)
            except ValueError:
                print("  [!] Invalid number.")
                continue
            w = checkThreshold(name, value)
            if w:
                print(f"  ⚠  WARNING: {w['message']}")
                print(f"     → {w['notes']}")
            elif name not in THRESHOLDS:
                print(f"  ('{name}' has no threshold defined)")
            else:
                print(f"  ✓  {name} = {value} is within safe bounds.")

        # ── quit ──────────────────────────────────────────────────────────────
        elif cmd in ("quit", "exit", "q"):
            print("Exiting debug mode.")
            break

        else:
            print("  Unknown command. Try: record, random, predict, status, check, quit")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--debug" in sys.argv:
        runDebugMode()
    else:
        runSocketLoop()

