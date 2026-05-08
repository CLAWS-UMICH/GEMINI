"""
test_warnings.py — Non-nominal injection test suite
=====================================================
Posts crafted telemetry payloads to the proxy's /inject endpoint and
simultaneously listens on the rover-telemetry socket event to confirm
the warning system fires (or stays quiet) as expected.

Usage:
    python test_warnings.py
    python test_warnings.py --host 172.27.175.241 --port 5001

Requires the modified app.py (with POST /inject) to be running.
"""

import argparse
import sys
import time
import threading
import requests
import socketio as sio_module

# ── Import the warning-system logic directly ──────────────────────────────────
# Adjust the import path if your file is named differently.
try:
    from gloria_test_script import (
        processTelemetry,
        clearHistory,
        RATE_FIELDS,
        THRESHOLDS,
        EARLY_WARNING_TIMESTEPS,
    )
    WARNING_MODULE = "gloria_test_script"
except ImportError:
    from predictive_warning_system import (
        processTelemetry,
        clearHistory,
        RATE_FIELDS,
        THRESHOLDS,
        EARLY_WARNING_TIMESTEPS,
    )
    WARNING_MODULE = "predictive_warning_system"


# ─────────────────────────────────────────────────────────────────────────────
# Test scenario definitions
# ─────────────────────────────────────────────────────────────────────────────

# Each scenario is a dict with:
#   name        — human-readable label
#   payload     — the telemetry dict to inject
#   expect_warn — list of field names that MUST appear in warnings
#   expect_ok   — list of field names that must NOT trigger warnings
#   description — what non-nominal condition this simulates

SCENARIOS: list[dict] = [
    # ── All nominal baseline ──────────────────────────────────────────────────
    {
        "name": "baseline_nominal",
        "description": "All values within safe range — expect zero warnings.",
        "payload": {
            "mission_elapsed_time": 0,
            "battery_level":    80.0,
            "oxygen_tank":      90.0,
            "oxygen_pressure":  2999.0,
            "coolant_storage":  95.0,
            "coolant_pressure": 500.0,
            "cabin_pressure":   4.0,
            "cabin_temperature": 21.0,
            "speed":            5.0,
            "pitch":            0.0,
            "roll":             10.0,
            "fan_pri_rpm":      30002.0,
            "fan_sec_rpm":      30002.0,
        },
        "expect_warn": [],
        "expect_ok":   ["battery_level", "oxygen_tank", "cabin_pressure"],
    },

    # ── Battery critically low ────────────────────────────────────────────────
    {
        "name": "battery_low",
        "description": "Battery at 10 % — below the 30 % threshold.",
        "payload": {
            "mission_elapsed_time": 1,
            "battery_level":    10.0,
            "oxygen_tank":      90.0,
            "oxygen_pressure":  2999.0,
            "coolant_storage":  95.0,
        },
        "expect_warn": ["battery_level"],
        "expect_ok":   ["oxygen_tank", "coolant_storage"],
    },

    # ── Oxygen tank depleted ──────────────────────────────────────────────────
    {
        "name": "oxygen_tank_low",
        "description": "O2 tank at 5 % — below the 25 % minimum.",
        "payload": {
            "mission_elapsed_time": 2,
            "battery_level":    80.0,
            "oxygen_tank":      5.0,
            "oxygen_pressure":  2999.0,
            "coolant_storage":  95.0,
        },
        "expect_warn": ["oxygen_tank"],
        "expect_ok":   ["battery_level"],
    },

    # ── Cabin pressure loss ───────────────────────────────────────────────────
    {
        "name": "cabin_pressure_low",
        "description": "Cabin pressure at 2.0 psi — below the 3.5 psi floor.",
        "payload": {
            "mission_elapsed_time": 3,
            "battery_level":    80.0,
            "cabin_pressure":   2.0,
            "coolant_storage":  95.0,
        },
        "expect_warn": ["cabin_pressure"],
        "expect_ok":   ["battery_level"],
    },

    # ── Cabin overpressure ────────────────────────────────────────────────────
    {
        "name": "cabin_pressure_high",
        "description": "Cabin pressure at 5.5 psi — above the 4.10 psi ceiling.",
        "payload": {
            "mission_elapsed_time": 4,
            "battery_level":    80.0,
            "cabin_pressure":   5.5,
        },
        "expect_warn": ["cabin_pressure"],
        "expect_ok":   ["battery_level"],
    },

    # ── Rover over-speed ──────────────────────────────────────────────────────
    {
        "name": "speed_exceeded",
        "description": "Rover speed at 25 m/s — above the 18 m/s limit.",
        "payload": {
            "mission_elapsed_time": 5,
            "battery_level":    80.0,
            "speed":            25.0,
        },
        "expect_warn": ["speed"],
        "expect_ok":   ["battery_level"],
    },

    # ── Dangerous pitch ───────────────────────────────────────────────────────
    {
        "name": "pitch_exceeded",
        "description": "Pitch at -70 deg — outside the ±50 deg safe band.",
        "payload": {
            "mission_elapsed_time": 6,
            "battery_level":    80.0,
            "pitch":           -70.0,
        },
        "expect_warn": ["pitch"],
        "expect_ok":   ["battery_level"],
    },

    # ── Fan failure ───────────────────────────────────────────────────────────
    {
        "name": "fan_rpm_low",
        "description": "Primary fan at 15000 rpm — below the 29999 rpm minimum.",
        "payload": {
            "mission_elapsed_time": 7,
            "battery_level":    80.0,
            "fan_pri_rpm":      15000.0,
        },
        "expect_warn": ["fan_pri_rpm"],
        "expect_ok":   ["battery_level"],
    },

    # ── Coolant storage low ───────────────────────────────────────────────────
    {
        "name": "coolant_low",
        "description": "Coolant storage at 50 % — below the 80 % minimum.",
        "payload": {
            "mission_elapsed_time": 8,
            "battery_level":    80.0,
            "coolant_storage":  50.0,
        },
        "expect_warn": ["coolant_storage"],
        "expect_ok":   ["battery_level"],
    },

    # ── Multiple simultaneous failures ────────────────────────────────────────
    {
        "name": "multi_failure",
        "description": "Battery low + O2 low + overspeed — three simultaneous warnings.",
        "payload": {
            "mission_elapsed_time": 9,
            "battery_level":    15.0,
            "oxygen_tank":      10.0,
            "speed":            30.0,
            "coolant_storage":  95.0,
        },
        "expect_warn": ["battery_level", "oxygen_tank", "speed"],
        "expect_ok":   ["coolant_storage"],
    },

    # ── Predictive: battery draining fast ────────────────────────────────────
    # Send three consecutive readings to build enough history for a slope,
    # then verify a PREDICTIVE warning is generated.
    {
        "name": "predictive_battery_drain",
        "description": (
            "Battery dropping 10 %/timestep from 50 → 30 → 10. "
            "Should trigger a PREDICTIVE warning on the third reading."
        ),
        "multi_step": [
            {"mission_elapsed_time": 10, "battery_level": 50.0, "oxygen_tank": 90.0, "coolant_storage": 95.0},
            {"mission_elapsed_time": 11, "battery_level": 30.0, "oxygen_tank": 90.0, "coolant_storage": 95.0},
            {"mission_elapsed_time": 12, "battery_level": 10.0, "oxygen_tank": 90.0, "coolant_storage": 95.0},
        ],
        "payload": None,   # unused when multi_step is present
        "expect_warn": ["battery_level"],
        "expect_ok":   [],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
INFO = "\033[94m·\033[0m"


def run_local_tests() -> tuple[int, int]:
    """
    Run all scenarios locally through processTelemetry() without touching
    the network. Returns (passed, failed).
    """
    print(f"\n{'='*60}")
    print(f"  LOCAL WARNING-LOGIC TESTS  (module: {WARNING_MODULE})")
    print(f"{'='*60}\n")

    passed = failed = 0

    for scenario in SCENARIOS:
        name        = scenario["name"]
        description = scenario["description"]
        expect_warn = set(scenario["expect_warn"])
        expect_ok   = set(scenario["expect_ok"])

        clearHistory()  # fresh history per scenario

        print(f"[ {name} ]")
        print(f"  {INFO} {description}")

        # ── multi-step scenario ───────────────────────────────────────────────
        steps = scenario.get("multi_step") or [scenario["payload"]]
        all_warnings: list[dict] = []
        for step in steps:
            ts = step.get("mission_elapsed_time", 0)
            all_warnings = processTelemetry(step, ts)

        triggered_fields = {w["valuename"] for w in all_warnings}

        # Check expected warnings fired
        scenario_passed = True
        for field in expect_warn:
            if field in triggered_fields:
                print(f"  {PASS}  '{field}' warning fired as expected.")
            else:
                print(f"  {FAIL}  '{field}' warning expected but NOT triggered.")
                scenario_passed = False

        # Check expected-ok fields did NOT fire
        for field in expect_ok:
            if field not in triggered_fields:
                print(f"  {PASS}  '{field}' correctly stayed nominal.")
            else:
                print(f"  {FAIL}  '{field}' fired unexpectedly.")
                scenario_passed = False

        # Print any extra warnings that fired (informational, not a failure)
        extras = triggered_fields - expect_warn - expect_ok
        for field in extras:
            w = next(w for w in all_warnings if w["valuename"] == field)
            print(f"  {INFO}  Extra warning: [{w['severity']}] {w['message']}")

        if scenario_passed:
            passed += 1
        else:
            failed += 1
        print()

    return passed, failed


def run_network_tests(host: str, port: int) -> tuple[int, int]:
    """
    For each scenario, POST the payload to /inject and listen on the
    rover-telemetry socket to verify the proxy emits it correctly.
    This confirms the round-trip through app.py, not just local logic.
    Returns (passed, failed).
    """
    base_url   = f"http://{host}:{port}"
    inject_url = f"{base_url}/inject"

    print(f"\n{'='*60}")
    print(f"  NETWORK ROUND-TRIP TESTS  ({base_url})")
    print(f"{'='*60}\n")

    passed = failed = 0

    for scenario in SCENARIOS:
        # Skip multi-step scenarios for network tests (they need sequential injects)
        steps = scenario.get("multi_step")
        payloads = steps if steps else [scenario["payload"]]

        name        = scenario["name"]
        description = scenario["description"]

        print(f"[ {name} ]")
        print(f"  {INFO} {description}")

        received_events: list[dict] = []
        event_ready = threading.Event()

        sio = sio_module.Client(logger=False, engineio_logger=False)

        @sio.on("rover-telemetry")
        def on_telemetry(data):
            if data.get("_injected"):
                received_events.append(data)
                event_ready.set()

        try:
            sio.connect(base_url, transports=["polling", "websocket"])
        except Exception as e:
            print(f"  {FAIL}  Could not connect to proxy: {e}\n")
            failed += 1
            continue

        try:
            for payload in payloads:
                event_ready.clear()
                resp = requests.post(inject_url, json=payload, timeout=5)
                if resp.status_code != 200:
                    print(f"  {FAIL}  /inject returned {resp.status_code}: {resp.text}\n")
                    failed += 1
                    sio.disconnect()
                    break
                # Wait up to 3 s for the event to arrive
                arrived = event_ready.wait(timeout=3.0)
                time.sleep(0.1)  # let any extra events flush

            else:
                if not received_events:
                    print(f"  {FAIL}  No rover-telemetry event received within timeout.\n")
                    failed += 1
                else:
                    last = received_events[-1]
                    print(f"  {PASS}  rover-telemetry event received with _injected=True.")
                    # Spot-check a couple of injected field values
                    check_payload = payloads[-1]
                    value_ok = True
                    for k, v in check_payload.items():
                        if k == "mission_elapsed_time":
                            continue
                        if k in last and abs(float(last[k]) - float(v)) < 0.01:
                            print(f"  {PASS}  Field '{k}' = {last[k]} matches injected value {v}.")
                        elif k in last:
                            print(f"  {FAIL}  Field '{k}' = {last[k]} but expected {v}.")
                            value_ok = False
                    if value_ok:
                        passed += 1
                    else:
                        failed += 1

        finally:
            sio.disconnect()

        print()

    return passed, failed


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Warning system test suite")
    parser.add_argument("--host", default="172.27.175.241", help="Proxy host IP")
    parser.add_argument("--port", default=5001, type=int,   help="Proxy port")
    parser.add_argument(
        "--mode",
        choices=["local", "network", "both"],
        default="both",
        help="local = logic only, network = round-trip via proxy, both = all",
    )
    args = parser.parse_args()

    total_passed = total_failed = 0

    if args.mode in ("local", "both"):
        p, f = run_local_tests()
        total_passed += p
        total_failed += f

    if args.mode in ("network", "both"):
        p, f = run_network_tests(args.host, args.port)
        total_passed += p
        total_failed += f

    print(f"\n{'='*60}")
    print(f"  RESULTS:  {total_passed} passed  /  {total_failed} failed")
    print(f"{'='*60}\n")

    sys.exit(0 if total_failed == 0 else 1)

