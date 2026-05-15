from collections.abc import Callable
from typing import Any

from src.responder.handlers import (
    handle_battery_level,
    handle_cabin_pressure,
    handle_cabin_temperature,
    handle_coolant_pressure,
    handle_coolant_storage,
    handle_distance_traveled,
    handle_external_temp,
    handle_heading,
    handle_heart_rate,
    handle_oxygen_pressure,
    handle_oxygen_tank,
    handle_rover_elapsed_time,
    handle_signal_strength,
    handle_speed,
    handle_sunlight,
    handle_surface_incline,
    handle_throttle,
    handle_warnings,
)

ResponseFn = Callable[[str, Any, dict], str]

REGISTRY: dict[str, ResponseFn] = {
    # EVA crew vitals (eva1 = primary astronaut)
    "vitals_heart_rate": handle_heart_rate,
    # Rover state
    "get_battery_level": handle_battery_level,
    "get_speed": handle_speed,
    "get_oxygen_pressure": handle_oxygen_pressure,
    "get_oxygen_tank": handle_oxygen_tank,
    "get_cabin_pressure": handle_cabin_pressure,
    "get_cabin_temperature": handle_cabin_temperature,
    "get_external_temp": handle_external_temp,
    "get_heading": handle_heading,
    "get_distance_traveled": handle_distance_traveled,
    "get_surface_incline": handle_surface_incline,
    "get_throttle": handle_throttle,
    "get_sunlight": handle_sunlight,
    "get_coolant_pressure": handle_coolant_pressure,
    "get_coolant_storage": handle_coolant_storage,
    "get_rover_elapsed_time": handle_rover_elapsed_time,
    # LTV
    "get_signal_strength": handle_signal_strength,
    # System warnings (TSS surfaces errors as a list of procedures, not per-subsystem flags)
    "get_warnings": handle_warnings,
}
