"""
Test runner for predictive_warning_system.py
=============================================
Loads snapshots from test_telemetry.json and runs them through the warning
system exactly as the live TSS polling loop would — no server needed.

Usage:
    python test_warnings.py
    python test_warnings.py test_telemetry.json   (to use a different file)
"""

import json
import sys
from predictive_warning_system import processTelemetry, clearHistory

# Load the JSON file (default: test_telemetry.json)
json_file = sys.argv[1] if len(sys.argv) > 1 else "test_telemetry.json"

with open(json_file) as f:
    snapshots = json.load(f)

print(f"Loaded {len(snapshots)} snapshots from {json_file}")
print("=" * 60)

clearHistory()

for snap in snapshots:
    timestep = snap.get("mission_elapsed_time", 0)
    warnings = processTelemetry(snap, timestep)

    if warnings:
        print(f"\n[t={timestep}]  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  [{w['severity']}] {w['message']}")
    else:
        print(f"[t={timestep}] All nominal.")
