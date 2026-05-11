from collections.abc import Callable
from typing import Any

from src.responder.handlers import (
    handle_batt_time_left,
    handle_battery_level,
    handle_errors_nav_system,
    handle_heart_rate,
    handle_signal_strength,
    handle_speed,
)

ResponseFn = Callable[[str, Any, dict], str]

REGISTRY: dict[str, ResponseFn] = {
    "vitals_heart_rate": handle_heart_rate,
    "vitals_batt_time_left": handle_batt_time_left,
    "get_battery_level": handle_battery_level,
    "get_speed": handle_speed,
    "get_signal_strength": handle_signal_strength,
    "get_errors_nav_system": handle_errors_nav_system,
}
