"""EVA-mode response registry — 45 entries keyed to intenteva.json.

Every EVA label is snake_case ending in `_eva1` or `_eva2`. The suffix
routes to `telemetry.eva1.<field>` vs `telemetry.eva2.<field>`. All
entries fit the template_handler pattern; no special cases.

Spec §8.
"""

from src.core.responder.template_handler import ResponseFn, template_handler


def _path_for(label: str) -> str:
    """Build the dot-delimited cache path for an EVA label.

    Convention: get_<field>_<evaN> → telemetry.<evaN>.<field>.

    Example:
        get_heart_rate_eva1     → telemetry.eva1.heart_rate
        get_oxy_pri_storage_eva2 → telemetry.eva2.oxy_pri_storage
    """
    assert label.startswith("get_") and (label.endswith("_eva1") or label.endswith("_eva2")), label
    crew = "eva1" if label.endswith("_eva1") else "eva2"
    field = label.removeprefix("get_").removesuffix(f"_{crew}")
    return f"telemetry.{crew}.{field}"


# Verified field paths (override the mechanical convention where TSS uses
# a different name). Phase 1 confirmed `telemetry.eva1.heart_rate` via
# test_handle_heart_rate_reads_eva1. Add more here as we observe live
# TTTDTT payloads.
_EVA_PATH_OVERRIDES: dict[str, str] = {
    # (empty for now — heart_rate already matches the mechanical path)
}


_EVA_LABELS: list[str] = [
    "get_battery_level_eva2",
    "get_co2_production_eva1", "get_co2_production_eva2",
    "get_coolant_gas_pressure_eva1", "get_coolant_gas_pressure_eva2",
    "get_coolant_liquid_pressure_eva1", "get_coolant_liquid_pressure_eva2",
    "get_coolant_storage_eva1", "get_coolant_storage_eva2",
    "get_eva_elapsed_time_eva1", "get_eva_elapsed_time_eva2",
    "get_fan_pri_rpm_eva1", "get_fan_pri_rpm_eva2",
    "get_fan_sec_rpm_eva1", "get_fan_sec_rpm_eva2",
    "get_heart_rate_eva1", "get_heart_rate_eva2",
    "get_helmet_pressure_co2_eva1", "get_helmet_pressure_co2_eva2",
    "get_oxy_consumption_eva1", "get_oxy_consumption_eva2",
    "get_oxy_pri_pressure_eva1", "get_oxy_pri_pressure_eva2",
    "get_oxy_pri_storage_eva1", "get_oxy_pri_storage_eva2",
    "get_oxy_sec_pressure_eva1", "get_oxy_sec_pressure_eva2",
    "get_oxy_sec_storage_eva1", "get_oxy_sec_storage_eva2",
    "get_primary_battery_level_eva1",
    "get_scrubber_a_co2_storage_eva1", "get_scrubber_a_co2_storage_eva2",
    "get_scrubber_b_co2_storage_eva1", "get_scrubber_b_co2_storage_eva2",
    "get_secondary_battery_level_eva1",
    "get_suit_pressure_co2_eva1", "get_suit_pressure_co2_eva2",
    "get_suit_pressure_other_eva1", "get_suit_pressure_other_eva2",
    "get_suit_pressure_oxy_eva1", "get_suit_pressure_oxy_eva2",
    "get_suit_pressure_total_eva1", "get_suit_pressure_total_eva2",
    "get_temperature_eva1", "get_temperature_eva2",
]


REGISTRY_EVA: dict[str, ResponseFn] = {
    label: template_handler(
        label,
        "eva",
        _EVA_PATH_OVERRIDES.get(label, _path_for(label)),
    )
    for label in _EVA_LABELS
}

assert len(REGISTRY_EVA) == 45, f"REGISTRY_EVA should have 45 entries, got {len(REGISTRY_EVA)}"
