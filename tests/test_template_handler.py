"""Tests for the template_handler factory."""

import pytest

from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
from src.core.telemetry.cache import TelemetryCache


@pytest.fixture
def cache_with_rover() -> TelemetryCache:
    c = TelemetryCache(stale_after_s=10.0)
    c.put("rover", {"pr_telemetry": {"primary_battery_level": 87.11, "lights_on": 1.0, "cabin_cooling": 0.0}})
    return c


@pytest.fixture
def cache_with_eva() -> TelemetryCache:
    c = TelemetryCache(stale_after_s=10.0)
    c.put("eva", {"telemetry": {"eva1": {"heart_rate": 78.4}, "eva2": {"heart_rate": 90.0}}})
    return c


def test_template_handler_formats_float(cache_with_rover):
    from src.core.responder.template_handler import template_handler

    h = template_handler("Get_battery_level", "rover", "pr_telemetry.primary_battery_level")
    result = h("hi", cache_with_rover, {"intent": "Get_battery_level", "confidence": 0.9})
    assert result == "The rover battery level is 87.1."


def test_template_handler_walks_nested_path(cache_with_eva):
    from src.core.responder.template_handler import template_handler

    h = template_handler("get_heart_rate_eva1", "eva", "telemetry.eva1.heart_rate")
    result = h("hi", cache_with_eva, {"intent": "get_heart_rate_eva1", "confidence": 0.9})
    assert result == "The heart rate for EVA 1 is 78.4."


def test_template_handler_returns_unavailable_when_cache_empty():
    from src.core.responder.template_handler import template_handler

    cache = TelemetryCache(stale_after_s=10.0)
    h = template_handler("Get_battery_level", "rover", "pr_telemetry.primary_battery_level")
    result = h("hi", cache, {"intent": "Get_battery_level", "confidence": 0.9})
    assert result == TELEMETRY_UNAVAILABLE_REPLY


def test_template_handler_returns_unavailable_on_missing_field():
    from src.core.responder.template_handler import template_handler

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {}})  # field absent
    h = template_handler("Get_battery_level", "rover", "pr_telemetry.primary_battery_level")
    result = h("hi", cache, {"intent": "Get_battery_level", "confidence": 0.9})
    assert result == TELEMETRY_UNAVAILABLE_REPLY


def test_template_handler_formats_bool_as_on_off(cache_with_rover):
    from src.core.responder.template_handler import template_handler

    # In live TTTDTT, on/off come as 1.0/0.0 floats. We render as "on"/"off".
    h_on = template_handler("get_lights_on", "rover", "pr_telemetry.lights_on")
    on = h_on("hi", cache_with_rover, {"intent": "get_lights_on", "confidence": 0.9})
    assert on == "The lights-on status is on."

    h_off = template_handler("get_cabin_cooling", "rover", "pr_telemetry.cabin_cooling")
    off = h_off("hi", cache_with_rover, {"intent": "get_cabin_cooling", "confidence": 0.9})
    assert off == "The cabin cooling setting is off."


def test_template_handler_formats_int_without_decimal():
    from src.core.responder.template_handler import template_handler

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"fan_pri_rpm": 1850}})
    h = template_handler("Get_fan_pri_rpm", "rover", "pr_telemetry.fan_pri_rpm")
    result = h("hi", cache, {"intent": "Get_fan_pri_rpm", "confidence": 0.9})
    assert result == "The primary fan RPM is 1850."


def test_unknown_intent_label_raises_at_factory_time():
    from src.core.responder.template_handler import template_handler

    with pytest.raises(KeyError):
        template_handler("nonexistent_label", "rover", "pr_telemetry.x")
