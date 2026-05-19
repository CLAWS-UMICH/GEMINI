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


# Bool-typed rover fields. TTTDTT emits these as 1.0/0.0 floats, so
# template_handler needs an explicit flag to render them as "on"/"off"
# rather than "1.00" / "0.00 percent".
_PR_BOOL_LABELS: frozenset[str] = frozenset({
    "Get_sim_running",
    "get_Dust_connected",
    "get_brakes",
    "get_cabin_cooling",
    "get_cabin_heating",
    "get_lights_on",
})


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
    **{label: template_handler(label, "rover", path, bool_field=label in _PR_BOOL_LABELS)
       for label, path in _PR_FIELD_PATHS.items()},
    **_PR_SPECIAL_HANDLERS,
}

assert len(REGISTRY_PR) == 43, f"REGISTRY_PR should have 43 entries, got {len(REGISTRY_PR)}"


# ---------------------------------------------------------------------------
# Phase 3: PR mode answers EVA-side telemetry queries too. We bolt the 45 EVA
# labels onto the 43 PR labels via the existing template_handler factory.
# Mapping pattern: get_<field>_eva{N} → telemetry.eva{N}.<field>; three
# asymmetric labels listed explicitly.
# ---------------------------------------------------------------------------
_EVA_FIELD_PATHS: dict[str, str] = {
    "get_heart_rate_eva1":               "telemetry.eva1.heart_rate",
    "get_heart_rate_eva2":               "telemetry.eva2.heart_rate",
    "get_temperature_eva1":              "telemetry.eva1.temperature",
    "get_temperature_eva2":              "telemetry.eva2.temperature",
    "get_oxy_pri_storage_eva1":          "telemetry.eva1.oxy_pri_storage",
    "get_oxy_pri_storage_eva2":          "telemetry.eva2.oxy_pri_storage",
    "get_oxy_sec_storage_eva1":          "telemetry.eva1.oxy_sec_storage",
    "get_oxy_sec_storage_eva2":          "telemetry.eva2.oxy_sec_storage",
    "get_oxy_pri_pressure_eva1":         "telemetry.eva1.oxy_pri_pressure",
    "get_oxy_pri_pressure_eva2":         "telemetry.eva2.oxy_pri_pressure",
    "get_oxy_sec_pressure_eva1":         "telemetry.eva1.oxy_sec_pressure",
    "get_oxy_sec_pressure_eva2":         "telemetry.eva2.oxy_sec_pressure",
    "get_suit_pressure_oxy_eva1":        "telemetry.eva1.suit_pressure_oxy",
    "get_suit_pressure_oxy_eva2":        "telemetry.eva2.suit_pressure_oxy",
    "get_suit_pressure_co2_eva1":        "telemetry.eva1.suit_pressure_co2",
    "get_suit_pressure_co2_eva2":        "telemetry.eva2.suit_pressure_co2",
    "get_suit_pressure_other_eva1":      "telemetry.eva1.suit_pressure_other",
    "get_suit_pressure_other_eva2":      "telemetry.eva2.suit_pressure_other",
    "get_suit_pressure_total_eva1":      "telemetry.eva1.suit_pressure_total",
    "get_suit_pressure_total_eva2":      "telemetry.eva2.suit_pressure_total",
    "get_helmet_pressure_co2_eva1":      "telemetry.eva1.helmet_pressure_co2",
    "get_helmet_pressure_co2_eva2":      "telemetry.eva2.helmet_pressure_co2",
    "get_fan_pri_rpm_eva1":              "telemetry.eva1.fan_pri_rpm",
    "get_fan_pri_rpm_eva2":              "telemetry.eva2.fan_pri_rpm",
    "get_fan_sec_rpm_eva1":              "telemetry.eva1.fan_sec_rpm",
    "get_fan_sec_rpm_eva2":              "telemetry.eva2.fan_sec_rpm",
    "get_scrubber_a_co2_storage_eva1":   "telemetry.eva1.scrubber_a_co2_storage",
    "get_scrubber_a_co2_storage_eva2":   "telemetry.eva2.scrubber_a_co2_storage",
    "get_scrubber_b_co2_storage_eva1":   "telemetry.eva1.scrubber_b_co2_storage",
    "get_scrubber_b_co2_storage_eva2":   "telemetry.eva2.scrubber_b_co2_storage",
    "get_coolant_storage_eva1":          "telemetry.eva1.coolant_storage",
    "get_coolant_storage_eva2":          "telemetry.eva2.coolant_storage",
    "get_coolant_gas_pressure_eva1":     "telemetry.eva1.coolant_gas_pressure",
    "get_coolant_gas_pressure_eva2":     "telemetry.eva2.coolant_gas_pressure",
    "get_coolant_liquid_pressure_eva1":  "telemetry.eva1.coolant_liquid_pressure",
    "get_coolant_liquid_pressure_eva2":  "telemetry.eva2.coolant_liquid_pressure",
    "get_oxy_consumption_eva1":          "telemetry.eva1.oxy_consumption",
    "get_oxy_consumption_eva2":          "telemetry.eva2.oxy_consumption",
    "get_co2_production_eva1":           "telemetry.eva1.co2_production",
    "get_co2_production_eva2":           "telemetry.eva2.co2_production",
    "get_eva_elapsed_time_eva1":         "telemetry.eva1.eva_elapsed_time",
    "get_eva_elapsed_time_eva2":         "telemetry.eva2.eva_elapsed_time",
    "get_battery_level_eva2":            "telemetry.eva2.battery_level",
    "get_primary_battery_level_eva1":    "telemetry.eva1.primary_battery_level",
    "get_secondary_battery_level_eva1":  "telemetry.eva1.secondary_battery_level",
}


REGISTRY_PR_FULL: dict[str, ResponseFn] = {
    **REGISTRY_PR,
    **{label: template_handler(label, "eva", path)
       for label, path in _EVA_FIELD_PATHS.items()},
}

assert len(REGISTRY_PR_FULL) == 88, (
    f"REGISTRY_PR_FULL should have 88 entries (43 PR + 45 EVA), got {len(REGISTRY_PR_FULL)}"
)
