"""Tests for the rebuilt REGISTRY_PR."""

import json
from pathlib import Path

import pytest

from src.core.responder.registry_pr import REGISTRY_PR, REGISTRY_PR_FULL
from src.core.telemetry.cache import TelemetryCache

CATALOG = Path(__file__).resolve().parents[1] / "models" / "intent_catalogs" / "intentPR.json"
requires_pr_catalog = pytest.mark.skipif(not CATALOG.exists(), reason="PR intent catalog not installed")


@requires_pr_catalog
def test_registry_covers_every_pr_label():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    missing = labels - set(REGISTRY_PR)
    assert not missing, f"PR labels not in registry: {sorted(missing)}"


@requires_pr_catalog
def test_registry_has_no_extraneous_labels():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    extra = set(REGISTRY_PR) - labels
    assert not extra, f"registry has labels not in intentPR.json: {sorted(extra)}"


def test_registry_has_43_entries():
    assert len(REGISTRY_PR) == 43


def test_get_battery_level_routes_to_template():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 87.11}})
    out = REGISTRY_PR["Get_battery_level"]("hi", cache, {"intent": "Get_battery_level", "confidence": 0.9})
    assert out == "The rover battery level is 87.11 percent."


def test_set_lights_on_routes_to_verbal_ack():
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_PR["set_lights_on"]("on the lights", cache,
                                        {"intent": "set_lights_on", "confidence": 0.9})
    assert "lights" in out.lower() and "on" in out.lower()


def test_get_lidar_routes_to_summary_handler():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"lidar": [1.0, 2.0, -1.0, 3.0] + [0.5] * 13}})
    out = REGISTRY_PR["get_lidar"]("scan", cache, {"intent": "get_lidar", "confidence": 0.9})
    assert "lidar" in out.lower()


@pytest.mark.parametrize("label", [
    "get_speed", "Get_oxygen_pressure", "Get_cabin_pressure",
    "get_heading", "get_throttle", "Get_external_temp",
])
def test_other_template_routes_unavailable_when_cache_empty(label):
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_PR[label]("hi", cache, {"intent": label, "confidence": 0.9})
    from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
    assert out == TELEMETRY_UNAVAILABLE_REPLY


def test_registry_pr_full_has_88_entries():
    assert len(REGISTRY_PR_FULL) == 88


def test_registry_pr_full_includes_every_pr_label():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    missing = labels - set(REGISTRY_PR_FULL)
    assert not missing, f"PR labels missing from REGISTRY_PR_FULL: {sorted(missing)}"


def test_registry_pr_full_includes_every_eva_label():
    eva_catalog = Path(__file__).resolve().parents[1] / "models" / "intent_catalogs" / "intenteva.json"
    if not eva_catalog.exists():
        pytest.skip("EVA catalog not installed")
    labels = {row["intent"] for row in json.loads(eva_catalog.read_text())}
    missing = labels - set(REGISTRY_PR_FULL)
    assert not missing, f"EVA labels missing from REGISTRY_PR_FULL: {sorted(missing)}"


def test_get_heart_rate_eva1_reads_eva_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})
    out = REGISTRY_PR_FULL["get_heart_rate_eva1"](
        "hi", cache, {"intent": "get_heart_rate_eva1", "confidence": 0.9}
    )
    assert "72" in out and "EVA 1" in out and "beats per minute" in out


def test_get_heart_rate_eva2_reads_eva_channel():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})
    out = REGISTRY_PR_FULL["get_heart_rate_eva2"](
        "hi", cache, {"intent": "get_heart_rate_eva2", "confidence": 0.9}
    )
    assert "80" in out and "EVA 2" in out


def test_get_oxy_pri_pressure_eva1_formats_with_psi_and_2dp():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"oxy_pri_pressure": 3.456789}}})
    out = REGISTRY_PR_FULL["get_oxy_pri_pressure_eva1"](
        "hi", cache, {"intent": "get_oxy_pri_pressure_eva1", "confidence": 0.9}
    )
    assert "3.46" in out
    assert "P S I" in out


def test_eva_label_unavailable_when_eva_cache_empty():
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_PR_FULL["get_temperature_eva1"](
        "hi", cache, {"intent": "get_temperature_eva1", "confidence": 0.9}
    )
    from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
    assert out == TELEMETRY_UNAVAILABLE_REPLY
