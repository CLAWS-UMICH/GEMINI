"""Tests for REGISTRY_EVA (NN-classifier era, full 87-label coverage).

EVA mode uses NNClassifier; REGISTRY_EVA covers every one of its 87 labels
so the AR team can dispatch on any wire `intent` without seeing
'unhandled'. Coverage mix:

  * 22 vitals_*  → template_handler, channel="eva"
  * 22 get_*     → template_handler, channel="rover"
  *  1 get_co2_scrubber → template_handler, channel="rover"
  *  2 orphans   → handle_signal_strength (ltv), handle_warnings (ltv_errors)
  *  2 composite → handle_rover_position, handle_last_known_position
  *  1 signal    → handle_signal_pings_left
  *  7 errors    → handle_error_category(keyword) per ltv_errors entry
  * ~30 acks     → verbal_ack(text) for menus/procedures/tasks/sets/etc.

Total: 87.
"""

import json
from pathlib import Path

import pytest

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache

TRAINING_DATA = Path(__file__).resolve().parents[1] / "data" / "intents" / "training_data.json"


def _nn_labels() -> set[str]:
    return {row["label"] for row in json.loads(TRAINING_DATA.read_text())["intents"]}


def test_registry_covers_every_nn_label():
    missing = _nn_labels() - set(REGISTRY_EVA)
    assert not missing, f"NN labels not in REGISTRY_EVA: {sorted(missing)}"


def test_registry_has_no_extraneous_labels():
    extra = set(REGISTRY_EVA) - _nn_labels()
    assert not extra, f"REGISTRY_EVA has labels not in NN training data: {sorted(extra)}"


def test_registry_size_matches_nn_label_count():
    assert len(REGISTRY_EVA) == len(_nn_labels()) == 87


# --- Telemetry handlers (template_handler-driven) --------------------------


def test_vitals_heart_rate_reads_eva_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.3}}})
    out = REGISTRY_EVA["vitals_heart_rate"](
        "hi", cache, {"intent": "vitals_heart_rate", "confidence": 0.99},
    )
    assert "72.3" in out and "heart rate" in out.lower()


def test_get_speed_reads_rover_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"speed": 4.5}})
    out = REGISTRY_EVA["get_speed"]("hi", cache, {"intent": "get_speed", "confidence": 0.99})
    assert "4.5" in out


def test_get_battery_level_resolves_primary_battery_field():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 65.4}})
    out = REGISTRY_EVA["get_battery_level"](
        "hi", cache, {"intent": "get_battery_level", "confidence": 0.99},
    )
    assert "65.4" in out


def test_get_oxygen_tank_resolves_oxygen_storage_field():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"oxygen_storage": 88.0}})
    out = REGISTRY_EVA["get_oxygen_tank"](
        "hi", cache, {"intent": "get_oxygen_tank", "confidence": 0.99},
    )
    assert "88" in out


# --- Orphan handlers ------------------------------------------------------


def test_get_signal_strength_reads_ltv_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv", {"signal": {"strength": 42.7}})
    out = REGISTRY_EVA["get_signal_strength"](
        "hi", cache, {"intent": "get_signal_strength", "confidence": 0.99},
    )
    assert "42.7" in out


def test_get_warnings_reads_ltv_errors_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv_errors", {"error_procedures": [
        {"description": "comms degraded", "needs_resolved": True},
    ]})
    out = REGISTRY_EVA["get_warnings"](
        "hi", cache, {"intent": "get_warnings", "confidence": 0.99},
    )
    assert "comms degraded" in out


# --- Hand-rolled composite handlers ---------------------------------------


def test_get_rover_position_returns_three_axes():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {
        "rover_pos_x": 12.3, "rover_pos_y": 45.6, "rover_pos_z": -1.2,
    }})
    out = REGISTRY_EVA["get_rover_position"](
        "where are we", cache,
        {"intent": "get_rover_position", "confidence": 0.99},
    )
    assert "12.3" in out and "45.6" in out and "-1.2" in out


def test_get_last_known_position_reads_ltv_location():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv", {"location": {"last_known_x": 7.5, "last_known_y": -3.2}})
    out = REGISTRY_EVA["get_last_known_position"](
        "hi", cache,
        {"intent": "get_last_known_position", "confidence": 0.99},
    )
    assert "7.5" in out and "-3.2" in out


def test_get_signal_pings_left_reads_ltv_signal():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv", {"signal": {"ping_requested": 3, "ping_unlimited_requested": 0}})
    out = REGISTRY_EVA["get_signal_pings_left"](
        "hi", cache,
        {"intent": "get_signal_pings_left", "confidence": 0.99},
    )
    # Either ping count is acceptable as a sensible report.
    assert "3" in out or "0" in out


# --- Error-category handlers ----------------------------------------------


def test_get_errors_dust_sensor_filters_by_keyword():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv_errors", {"error_procedures": [
        {"description": "Dust sensor offline", "needs_resolved": True},
        {"description": "Power distribution fault", "needs_resolved": True},
    ]})
    out = REGISTRY_EVA["get_errors_dust_sensor"](
        "hi", cache,
        {"intent": "get_errors_dust_sensor", "confidence": 0.99},
    )
    assert "Dust sensor offline" in out
    assert "Power distribution" not in out


def test_get_errors_dust_sensor_returns_none_message_when_clear():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv_errors", {"error_procedures": []})
    out = REGISTRY_EVA["get_errors_dust_sensor"](
        "hi", cache,
        {"intent": "get_errors_dust_sensor", "confidence": 0.99},
    )
    assert "no" in out.lower() or "clear" in out.lower() or "none" in out.lower()


# --- Verbal acks ----------------------------------------------------------


@pytest.mark.parametrize("label,expected_keyword", [
    ("open_menu_vitals",         "vitals"),
    ("open_menu_navigation",     "navigation"),
    ("start_procedure_erm",      "erm"),
    ("Add_task",                 "task"),
    ("Add_waypoint",             "waypoint"),
    ("Set_navigation_target",    "navigation"),
    ("close_menu",               "menu"),
    ("undo",                     "undo"),
    ("ping_ltv",                 "ltv"),
    ("set_lights_on",            "light"),
])
def test_verbal_ack_returns_descriptive_string(label, expected_keyword):
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_EVA[label]("hi", cache, {"intent": label, "confidence": 0.99})
    assert isinstance(out, str) and out
    assert expected_keyword.lower() in out.lower()


# --- Cache-empty parametrize for telemetry handlers ----------------------


@pytest.mark.parametrize("label", [
    "vitals_heart_rate", "vitals_co2_production", "get_speed",
    "get_battery_level", "get_signal_strength", "get_warnings",
    "get_rover_position", "get_last_known_position", "get_signal_pings_left",
])
def test_cache_empty_returns_telemetry_unavailable(label):
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_EVA[label]("hi", cache, {"intent": label, "confidence": 0.99})
    assert out == TELEMETRY_UNAVAILABLE_REPLY
