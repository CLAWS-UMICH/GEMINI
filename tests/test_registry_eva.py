"""Tests for the rebuilt REGISTRY_EVA."""

import json
from pathlib import Path

import pytest

from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache

CATALOG = Path(__file__).resolve().parents[1] / "models" / "intent_catalogs" / "intenteva.json"


def test_registry_covers_every_eva_label():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    missing = labels - set(REGISTRY_EVA)
    assert not missing, f"EVA labels not in registry: {sorted(missing)}"


def test_registry_has_no_extraneous_labels():
    labels = {row["intent"] for row in json.loads(CATALOG.read_text())}
    extra = set(REGISTRY_EVA) - labels
    assert not extra, f"registry has labels not in intenteva.json: {sorted(extra)}"


def test_registry_has_45_entries():
    assert len(REGISTRY_EVA) == 45


def test_heart_rate_eva1_reads_eva1_branch():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 78.4}, "eva2": {"heart_rate": 90.0}}})
    out = REGISTRY_EVA["get_heart_rate_eva1"]("hi", cache,
                                              {"intent": "get_heart_rate_eva1", "confidence": 0.9})
    assert out == "The heart rate for EVA 1 is 78.4."


def test_heart_rate_eva2_reads_eva2_branch():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 78.4}, "eva2": {"heart_rate": 90.0}}})
    out = REGISTRY_EVA["get_heart_rate_eva2"]("hi", cache,
                                              {"intent": "get_heart_rate_eva2", "confidence": 0.9})
    assert out == "The heart rate for EVA 2 is 90.0."


@pytest.mark.parametrize("label", [
    "get_oxy_pri_storage_eva1", "get_suit_pressure_co2_eva2",
    "get_eva_elapsed_time_eva1", "get_helmet_pressure_co2_eva2",
])
def test_template_routes_unavailable_when_cache_empty(label):
    cache = TelemetryCache(stale_after_s=10.0)
    out = REGISTRY_EVA[label]("hi", cache, {"intent": label, "confidence": 0.9})
    from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
    assert out == TELEMETRY_UNAVAILABLE_REPLY
