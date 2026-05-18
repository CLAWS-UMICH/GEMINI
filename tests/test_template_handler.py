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
    assert result == "The rover battery level is 87.11 percent."


def test_template_handler_walks_nested_path(cache_with_eva):
    from src.core.responder.template_handler import template_handler

    h = template_handler("get_heart_rate_eva1", "eva", "telemetry.eva1.heart_rate")
    result = h("hi", cache_with_eva, {"intent": "get_heart_rate_eva1", "confidence": 0.9})
    assert result == "The heart rate for EVA 1 is 78.40 beats per minute."


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

    # In live TTTDTT, on/off come as 1.0/0.0 floats. Bool intents are
    # flagged so the formatter renders the float as "on"/"off"; measurement
    # intents passing through 0.0 stay as numbers.
    h_on = template_handler(
        "get_lights_on", "rover", "pr_telemetry.lights_on", bool_field=True
    )
    on = h_on("hi", cache_with_rover, {"intent": "get_lights_on", "confidence": 0.9})
    assert on == "The lights-on status is on."

    h_off = template_handler(
        "get_cabin_cooling", "rover", "pr_telemetry.cabin_cooling", bool_field=True
    )
    off = h_off("hi", cache_with_rover, {"intent": "get_cabin_cooling", "confidence": 0.9})
    assert off == "The cabin cooling setting is off."


def test_template_handler_measurement_at_zero_does_not_fold_to_off():
    """Regression: a real measurement equal to 0.0 must render as "0.00 <unit>",
    not "off". The bool-fold only fires when bool_field=True at the registry."""
    from src.core.responder.template_handler import template_handler

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"suit_pressure_other": 0.0}}})
    h = template_handler(
        "vitals_suit_pressure_other", "eva", "telemetry.eva1.suit_pressure_other"
    )
    result = h("hi", cache, {"intent": "vitals_suit_pressure_other", "confidence": 0.9})
    assert result == "The other suit pressure is 0.00 P S I."


def test_template_handler_formats_int_without_decimal():
    from src.core.responder.template_handler import template_handler

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"fan_pri_rpm": 1850}})
    h = template_handler("Get_fan_pri_rpm", "rover", "pr_telemetry.fan_pri_rpm")
    result = h("hi", cache, {"intent": "Get_fan_pri_rpm", "confidence": 0.9})
    assert result == "The primary fan is 1850 R P M."


def test_unknown_intent_label_raises_at_factory_time():
    from src.core.responder.template_handler import template_handler

    with pytest.raises(KeyError):
        template_handler("nonexistent_label", "rover", "pr_telemetry.x")
