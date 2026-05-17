from __future__ import annotations

import sys
from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))


def nominal_telemetry(**overrides):
    telemetry = {
        "rover_elapsed_time": 100.0,
        "battery_level": 80,
        "oxygen_tank": 90,
        "oxygen_pressure": 2999,
        "coolant_storage": 95,
        "cabin_pressure": 4.0,
        "cabin_temperature": 21,
        "speed": 5,
        "pitch": 0,
        "roll": 0,
        "distance_from_base": 500,
        "heart_rate": 80,
    }
    telemetry.update(overrides)
    return telemetry


def nested_packet(**overrides):
    return {"pr_telemetry": nominal_telemetry(**overrides)}


def alert_for(alerts, metric):
    matches = [alert for alert in alerts if alert["metric"] == metric]
    assert len(matches) == 1
    return matches[0]
