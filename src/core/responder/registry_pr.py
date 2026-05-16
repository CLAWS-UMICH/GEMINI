"""PR-mode response registry — 43 entries keyed to intentPR.json.

Layout: a `_PR_FIELD_PATHS` table drives template_handler() generation
for the ~36 "format a single value" intents. Hand-rolled handlers
(handle_lidar + 6 set_*) slot in for the rest.

Spec §8.
"""

from src.core.responder.handlers_pr import (
    handle_lidar,
    handle_set_cabin_cooling_off,
    handle_set_cabin_cooling_on,
    handle_set_cabin_heating_off,
    handle_set_cabin_heating_on,
    handle_set_lights_off,
    handle_set_lights_on,
)
from src.core.responder.template_handler import ResponseFn, template_handler


# Maps label → field path inside the cached "rover" payload (pr_telemetry.*).
# Verified-against-live paths are marked V; others are mechanical
# strip-prefix-and-lowercase and rely on cache-miss fallback.
_PR_FIELD_PATHS: dict[str, str] = {
    # V (verified in Phase 1 handlers / test_dispatch.py)
    "Get_battery_level":          "pr_telemetry.primary_battery_level",
    "Get_cabin_pressure":         "pr_telemetry.cabin_pressure",
    "Get_coolant_pressure":       "pr_telemetry.coolant_pressure",
    "Get_coolant_storage":        "pr_telemetry.coolant_storage",
    "Get_external_temp":          "pr_telemetry.external_temp",
    "Get_oxygen_pressure":        "pr_telemetry.oxygen_pressure",
    "Get_oxygen_tank":            "pr_telemetry.oxygen_storage",
    "Get_rover_elapsed_time":     "pr_telemetry.rover_elapsed_time",
    "get_cabin_temperature":      "pr_telemetry.cabin_temperature",
    "get_distance_traveled":      "pr_telemetry.distance_traveled",
    "get_heading":                "pr_telemetry.heading",
    "get_speed":                  "pr_telemetry.speed",
    "get_sunlight":               "pr_telemetry.sunlight",
    "get_surface_incline":        "pr_telemetry.surface_incline",
    "get_throttle":               "pr_telemetry.throttle",
    # Mechanical (verify against TTTDTT in Task 11)
    "Get_cabin_temperature_target": "pr_telemetry.cabin_temperature_target",
    "Get_distance_from_base":       "pr_telemetry.distance_from_base",
    "Get_fan_pri_rpm":              "pr_telemetry.fan_pri_rpm",
    "Get_fan_sec_rpm":              "pr_telemetry.fan_sec_rpm",
    "Get_oxygen_storage":           "pr_telemetry.oxygen_storage",
    "Get_primary_battery_level":    "pr_telemetry.primary_battery_level",
    "Get_scrubber_a_co2_storage":   "pr_telemetry.scrubber_a_co2_storage",
    "Get_scrubber_b_co2_storage":   "pr_telemetry.scrubber_b_co2_storage",
    "Get_secondary_battery_level":  "pr_telemetry.secondary_battery_level",
    "Get_sim_running":              "pr_telemetry.sim_running",
    "get_Dust_connected":           "pr_telemetry.dust_connected",
    "get_brakes":                   "pr_telemetry.brakes",
    "get_cabin_cooling":            "pr_telemetry.cabin_cooling",
    "get_cabin_heating":            "pr_telemetry.cabin_heating",
    "get_lights_on":                "pr_telemetry.lights_on",
    "get_pitch":                    "pr_telemetry.pitch",
    "get_roll":                     "pr_telemetry.roll",
    "get_rover_pos_x":              "pr_telemetry.rover_pos_x",
    "get_rover_pos_y":              "pr_telemetry.rover_pos_y",
    "get_rover_pos_z":              "pr_telemetry.rover_pos_z",
    "get_steering":                 "pr_telemetry.steering",
}

# Hand-rolled handlers, indexed by label.
_PR_SPECIAL_HANDLERS: dict[str, ResponseFn] = {
    "get_lidar":             handle_lidar,
    "set_cabin_cooling_off": handle_set_cabin_cooling_off,
    "set_cabin_cooling_on":  handle_set_cabin_cooling_on,
    "set_cabin_heating_off": handle_set_cabin_heating_off,
    "set_cabin_heating_on":  handle_set_cabin_heating_on,
    "set_lights_off":        handle_set_lights_off,
    "set_lights_on":         handle_set_lights_on,
}

REGISTRY_PR: dict[str, ResponseFn] = {
    **{label: template_handler(label, "rover", path) for label, path in _PR_FIELD_PATHS.items()},
    **_PR_SPECIAL_HANDLERS,
}

assert len(REGISTRY_PR) == 43, f"REGISTRY_PR should have 43 entries, got {len(REGISTRY_PR)}"
