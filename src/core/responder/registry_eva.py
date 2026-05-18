"""EVA-mode response registry — full NN 87-label coverage.

EVA runs NNClassifier; this registry covers every NN label so the AR
team can dispatch on any wire `intent` field without seeing 'unhandled'.

Composition:
  * 22 vitals_*       → template_handler, channel="eva", telemetry.eva1.<field>
  * 23 get_* (rover)  → template_handler, channel="rover", pr_telemetry.<field>
                        (mirrors verified mappings from registry_pr.py)
  *  2 orphans        → handle_signal_strength (ltv), handle_warnings (ltv_errors)
  *  3 composites     → handle_rover_position, handle_last_known_position,
                        handle_signal_pings_left
  *  7 error filters  → handle_error_category(keyword, label) per ltv_errors entry
  * 30 verbal acks    → menus, procedures, tasks/waypoints/nav, sets,
                        close_menu, undo, ping_ltv, Get_coordinates
                        (Unity does the real work off the wire intent)

Total: 87.
"""

from src.core.responder.handlers_eva import (
    handle_error_category,
    handle_last_known_position,
    handle_rover_position,
    handle_signal_pings_left,
    verbal_ack,
)
from src.core.responder.handlers_pr import handle_signal_strength, handle_warnings
from src.core.responder.template_handler import ResponseFn, template_handler


# ---------------------------------------------------------------------------
# Suit telemetry — `vitals_<field>` → `telemetry.eva1.<field>`.
# Verified: heart_rate (Phase 1). Others mechanical; cache-miss fallback
# handles any name drift. The trailing 2 (oxy_time_left, batt_time_left)
# are derived values; will fall through to TELEMETRY_UNAVAILABLE until
# computed upstream.
# ---------------------------------------------------------------------------
_EVA_SUIT_LABELS: list[str] = [
    "vitals_heart_rate", "vitals_temperature",
    "vitals_oxy_pri_storage", "vitals_oxy_sec_storage",
    "vitals_oxy_pri_pressure", "vitals_oxy_sec_pressure",
    "vitals_suit_pressure_total", "vitals_suit_pressure_oxy",
    "vitals_suit_pressure_co2", "vitals_suit_pressure_other",
    "vitals_helmet_pressure_co2",
    "vitals_fan_pri_rpm", "vitals_fan_sec_rpm",
    "vitals_scrubber_a_co2_storage", "vitals_scrubber_b_co2_storage",
    "vitals_coolant_storage", "vitals_coolant_gas_pressure",
    "vitals_coolant_liquid_pressure",
    "vitals_oxy_consumption", "vitals_co2_production",
    "vitals_oxy_time_left", "vitals_batt_time_left",
]


def _eva_suit_path(label: str) -> str:
    assert label.startswith("vitals_"), label
    return f"telemetry.eva1.{label.removeprefix('vitals_')}"


# ---------------------------------------------------------------------------
# Rover telemetry queries (accessible from the EVA-side astronaut interface).
# Field paths mirror the verified entries in registry_pr.py:_PR_FIELD_PATHS.
# Two mappings diverge from strip-prefix:
#   get_battery_level  → primary_battery_level   (verified Phase 1)
#   get_oxygen_tank    → oxygen_storage          (verified Phase 1)
# get_co2_scrubber maps to scrubber A storage as the closest semantic match.
# ---------------------------------------------------------------------------
# Bool-typed rover fields. TTTDTT emits these as 1.0/0.0 floats, so
# template_handler needs an explicit flag to render them as "on"/"off"
# rather than "1.00" / "0.00 percent".
_EVA_BOOL_LABELS: frozenset[str] = frozenset({
    "get_cabin_cooling",
    "get_cabin_heating",
    "get_lights_on",
})


_EVA_ROVER_PATHS: dict[str, str] = {
    "get_battery_level":      "pr_telemetry.primary_battery_level",
    "get_cabin_pressure":     "pr_telemetry.cabin_pressure",
    "get_coolant_pressure":   "pr_telemetry.coolant_pressure",
    "get_coolant_storage":    "pr_telemetry.coolant_storage",
    "get_external_temp":      "pr_telemetry.external_temp",
    "get_oxygen_pressure":    "pr_telemetry.oxygen_pressure",
    "get_oxygen_tank":        "pr_telemetry.oxygen_storage",
    "get_rover_elapsed_time": "pr_telemetry.rover_elapsed_time",
    "get_cabin_temperature":  "pr_telemetry.cabin_temperature",
    "get_distance_traveled":  "pr_telemetry.distance_traveled",
    "get_heading":            "pr_telemetry.heading",
    "get_speed":              "pr_telemetry.speed",
    "get_sunlight":           "pr_telemetry.sunlight",
    "get_surface_incline":    "pr_telemetry.surface_incline",
    "get_throttle":           "pr_telemetry.throttle",
    "get_distance_from_base": "pr_telemetry.distance_from_base",
    "get_fan_pri_rpm":        "pr_telemetry.fan_pri_rpm",
    "get_fan_sec_rpm":        "pr_telemetry.fan_sec_rpm",
    "get_steering":           "pr_telemetry.steering",
    "get_cabin_cooling":      "pr_telemetry.cabin_cooling",
    "get_cabin_heating":      "pr_telemetry.cabin_heating",
    "get_lights_on":          "pr_telemetry.lights_on",
    "get_co2_scrubber":       "pr_telemetry.scrubber_a_co2_storage",
}


# ---------------------------------------------------------------------------
# Hand-rolled + orphan + error-category handlers.
# Error keywords are case-insensitive substring matches against
# error_procedures[].description; tune in handlers_eva.py if the live
# ltv_errors payload uses different terminology.
# ---------------------------------------------------------------------------
_EVA_SPECIAL_HANDLERS: dict[str, ResponseFn] = {
    "get_signal_strength":      handle_signal_strength,
    "get_warnings":             handle_warnings,
    "get_rover_position":       handle_rover_position,
    "get_last_known_position":  handle_last_known_position,
    "get_signal_pings_left":    handle_signal_pings_left,
    "get_errors_recovery_mode": handle_error_category("recovery", "recovery mode"),
    "get_errors_dust_sensor":   handle_error_category("dust", "dust sensor"),
    "get_errors_power_distribution":
        handle_error_category("power", "power distribution"),
    "get_errors_nav_system":    handle_error_category("nav", "navigation"),
    "get_errors_electronic_heater":
        handle_error_category("heater", "electronic heater"),
    "get_errors_comms":         handle_error_category("comm", "comms"),
    "get_errors_fuse":          handle_error_category("fuse", "fuse"),
}


# ---------------------------------------------------------------------------
# Verbal acks — Unity dispatches the real action off the wire `intent`;
# Python's `response` is the TTS confirmation. NN does not extract
# parameters, so acks are generic (no task/waypoint name interpolation).
# ---------------------------------------------------------------------------
_EVA_ACKS: dict[str, str] = {
    "open_menu_vitals":           "Opening vitals menu.",
    "open_menu_navigation":       "Opening navigation menu.",
    "open_menu_tasks":            "Opening tasks menu.",
    "open_menu_uia":              "Opening UIA menu.",
    "open_menu_messaging":        "Opening messaging menu.",
    "open_menu_geosamples":       "Opening geosamples menu.",
    "open_menu_rover":            "Opening rover menu.",
    "open_menu_voice_assistant":  "Opening voice assistant menu.",
    "close_menu":                 "Closing menu.",
    "undo":                       "Undoing last action.",
    "Set_navigation_target":      "Setting navigation target.",
    "reroute_navigation":         "Rerouting navigation.",
    "Get_coordinates":            "Reading coordinates.",
    "Add_waypoint":               "Adding waypoint.",
    "Delete_waypoint":            "Deleting waypoint.",
    "Add_task":                   "Adding task.",
    "Complete_task":              "Marking task complete.",
    "Delete_task":                "Deleting task.",
    "start_procedure_uia_egress":         "Starting UIA egress procedure.",
    "start_procedure_uia_ingress":        "Starting UIA ingress procedure.",
    "start_procedure_erm":                "Starting ERM procedure.",
    "start_procedure_system_diagnosis":   "Starting system diagnosis procedure.",
    "start_procedure_system_restart":     "Starting system restart procedure.",
    "start_procedure_physical_repair_task":
        "Starting physical repair procedure.",
    "start_procedure_final_system_checks":
        "Starting final system checks procedure.",
    "set_cabin_heating":          "Setting cabin heating.",
    "set_cabin_cooling":          "Setting cabin cooling.",
    "set_co2_scrubber":           "Setting CO2 scrubber.",
    "set_lights_on":              "Setting lights on.",
    "ping_ltv":                   "Pinging LTV.",
}


REGISTRY_EVA: dict[str, ResponseFn] = {
    **{label: template_handler(label, "eva", _eva_suit_path(label))
       for label in _EVA_SUIT_LABELS},
    **{label: template_handler(label, "rover", path, bool_field=label in _EVA_BOOL_LABELS)
       for label, path in _EVA_ROVER_PATHS.items()},
    **_EVA_SPECIAL_HANDLERS,
    **{label: verbal_ack(text) for label, text in _EVA_ACKS.items()},
}

assert len(REGISTRY_EVA) == 87, f"REGISTRY_EVA should have 87 entries, got {len(REGISTRY_EVA)}"
