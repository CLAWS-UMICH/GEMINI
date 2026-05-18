"""Tests for the rebuilt REGISTRY_PR."""

import json
from pathlib import Path

import pytest

from src.core.responder.registry_pr import REGISTRY_PR
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
