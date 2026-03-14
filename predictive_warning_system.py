"""
Predictive Warning System — Pressurized Rover
==============================================
Reads live telemetry from the TSS server and runs two warning sub-systems:

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

  TSS integration:
      processTelemetry(telemetry, timestep)  → list[warning dict]
          Pass the full pr_telemetry dict from the TSS response. Records every
          tracked field in Sub-system 1 and checks all thresholds in Sub-system 2.

  Configuration:
      TSS_BASE_URL           — set to your TSS server address (default: localhost:14141)
      POLL_INTERVAL          — seconds between telemetry polls (default: 1.0)
      TEAM_NUMBER            — your TSS team number
      RATE_FIELDS            — which fields to track with Sub-system 1
      EARLY_WARNING_TIMESTEPS — how soon a projected breach triggers a warning
"""

import time
import requests
from collections import defaultdict
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — edit these to match your environment
# ─────────────────────────────────────────────────────────────────────────────

TSS_BASE_URL  = "http://172.20.182.43:14141"   # TSS server address
POLL_INTERVAL = 1.0                        # seconds between polls
TEAM_NUMBER   = 1                          # your team number for the TSS endpoint

# Fields to track with Sub-system 1 (rate-of-change), mapped to the critical
# target value that triggers a predictive warning. Field names match the TSS
# pr_telemetry keys from ROVER.json.
RATE_FIELDS: dict[str, float] = {
    "battery_level":           0,     # warn when projected to hit 0 %
    "oxygen_tank":             20,    # warn when projected to hit 20 %
    "oxygen_pressure":         600,   # warn when projected to drop to 600 psi
    "pr_coolant_level":        20,    # warn when projected to hit 20 %
    "pr_coolant_tank":         20,    # warn when projected to hit 20 %
    "solar_panel_dust_accum":  90,    # warn when projected to hit 90 % dust
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
    a live TSS snapshot. Only call this directly for isolated testing.
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

    # ── Power ────────────────────────────────────────────────────────────────
    "battery_level": {
        "low":   20,
        "high":  None,
        "unit":  "%",
        "notes": "Initiate return-to-base below 20 %. Below 10 % is critical.",
    },
    "power_consumption_rate": {
        "low":   None,
        "high":  5.0,   # kW — team should calibrate this to actual rover specs
        "unit":  "kW",
        "notes": "Unusually high power consumption — check active systems.",
    },

    # ── Oxygen ───────────────────────────────────────────────────────────────
    "oxygen_tank": {
        "low":   20,
        "high":  None,
        "unit":  "%",
        "notes": "O2 tank below 20 % — begin abort protocol.",
    },
    "oxygen_pressure": {
        "low":   600,
        "high":  3500,
        "unit":  "psi",
        "notes": "O2 supply pressure outside nominal range (600–3500 psi).",
    },
    "oxygen_levels": {
        "low":   19.5,  # % — OSHA minimum safe atmospheric O2 for breathing
        "high":  23.5,  # % — above this, fire risk increases significantly
        "unit":  "%",
        "notes": "Cabin O2 concentration outside safe breathing range (19.5–23.5 %).",
    },

    # ── Cabin Atmosphere ─────────────────────────────────────────────────────
    "cabin_pressure": {
        "low":   3.5,
        "high":  16.0,
        "unit":  "psi",
        "notes": "Cabin pressure outside safe range — possible leak or over-pressurisation.",
    },
    "cabin_temperature": {
        "low":   15,
        "high":  35,
        "unit":  "°C",
        "notes": "Crew comfort and cognitive performance band: 15–35 °C.",
    },

    # ── Coolant System ───────────────────────────────────────────────────────
    "pr_coolant_pressure": {
        "low":   -700,  # TSS reports coolant pressure as negative in some states
        "high":   700,
        "unit":  "psi",
        "notes": "Coolant pressure outside safe range — possible leak or blockage.",
    },
    "pr_coolant_level": {
        "low":   20,
        "high":  None,
        "unit":  "%",
        "notes": "Coolant level below 20 % — thermal runaway risk.",
    },
    "pr_coolant_tank": {
        "low":   20,
        "high":  None,
        "unit":  "%",
        "notes": "Coolant tank reserve below 20 %.",
    },

    # ── Fans ─────────────────────────────────────────────────────────────────
    "ac_fan_pri": {
        "low":   1000,
        "high":  None,
        "unit":  "RPM",
        "notes": "Primary fan stall — CO2 and thermal buildup risk.",
    },
    "ac_fan_sec": {
        "low":   1000,
        "high":  None,
        "unit":  "RPM",
        "notes": "Secondary fan stall — CO2 and thermal buildup risk.",
    },

    # ── Solar / Dust ─────────────────────────────────────────────────────────
    "solar_panel_efficiency": {
        "low":   20,
        "high":  None,
        "unit":  "%",
        "notes": "Solar panel efficiency critically low — check dust accumulation.",
    },
    "solar_panel_dust_accum": {
        "low":   None,
        "high":  75,
        "unit":  "%",
        "notes": "Solar panel dust accumulation high — efficiency degraded, cleaning needed.",
    },

    # ── External Environment ─────────────────────────────────────────────────
    "external_temp": {
        "low":   -150,
        "high":   130,
        "unit":  "°C",
        "notes": "Extreme external temperature — verify thermal protection systems.",
    },
    "surface_incline": {
        "low":   None,
        "high":  20,
        "unit":  "deg",
        "notes": "Steep incline (>20°) — increased tip-over risk.",
    },
    "speed": {
        "low":   None,
        "high":  20,
        "unit":  "km/h",
        "notes": "Rover speed exceeds safe navigation limit.",
    },

    # ── Navigation ───────────────────────────────────────────────────────────
    "distance_from_base": {
        "low":   None,
        "high":  5000,
        "unit":  "m",
        "notes": "Rover may be beyond safe return range given current battery level.",
    },
    "point_of_no_return": {
        "low":   None,
        "high":  0,     # any positive value means the flag is set
        "unit":  "flag",
        "notes": "Rover has passed the point of no return.",
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
    readings : dict — the pr_telemetry object from the TSS response

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
# Combined: process one full telemetry snapshot from the TSS server
# ─────────────────────────────────────────────────────────────────────────────

def processTelemetry(telemetry: dict, timestep: float) -> list[dict]:
    """
    Main entry point. Call this every time you receive a telemetry update
    from the TSS server.

    Parameters
    ----------
    telemetry : dict  — the pr_telemetry object from the TSS server response
    timestep  : float — use mission_elapsed_time from telemetry, or a poll counter

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
# TSS server fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetchTelemetry() -> dict | None:
    """
    Fetch the current pr_telemetry snapshot from the TSS server.
    Returns the telemetry dict, or None if the request fails.

    Adjust the URL path if your TSS version uses a different endpoint.
    """
    url = f"{TSS_BASE_URL}/json_data/teams/{TEAM_NUMBER}/rover"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        # Handle both { "pr_telemetry": {...} } and flat responses
        return data.get("pr_telemetry", data)
    except requests.RequestException as e:
        print(f"[ERROR] Could not reach TSS at {url}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Polling loop — run this as your main process
# ─────────────────────────────────────────────────────────────────────────────

def runPollingLoop() -> None:
    """
    Continuously poll the TSS server, process each telemetry snapshot,
    and print any warnings. Press Ctrl+C to stop.
    """
    print(f"Predictive Warning System started")
    print(f"Polling: {TSS_BASE_URL}  every {POLL_INTERVAL}s  (team {TEAM_NUMBER})")
    print(f"Rate tracking: {list(RATE_FIELDS.keys())}")
    print("-" * 60)

    poll_count = 0

    try:
        while True:
            telemetry = fetchTelemetry()

            if telemetry is None:
                time.sleep(POLL_INTERVAL)
                continue

            # Prefer mission_elapsed_time from the server as the timestep
            timestep = telemetry.get("mission_elapsed_time", poll_count)

            warnings = processTelemetry(telemetry, timestep)

            if warnings:
                print(f"\n[t={timestep}]  {len(warnings)} warning(s):")
                for w in warnings:
                    print(f"  [{w['severity']}] {w['message']}")
                    if w.get("notes"):
                        print(f"           → {w['notes']}")
            else:
                print(f"[t={timestep}] All nominal.")

            poll_count += 1
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nWarning system stopped.")


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
        runPollingLoop()
