from src.core.responder import dispatch
from src.core.responder.fallback import (
    LOW_CONFIDENCE_REPLY,
    TELEMETRY_UNAVAILABLE_REPLY,
    UNKNOWN_INTENT_REPLY,
)
from src.core.telemetry.cache import TelemetryCache


def test_low_confidence_returns_low_conf_reply():
    cache = TelemetryCache()
    classification = {"intent": "foo", "confidence": 0.10}
    registry = {"foo": lambda *_: "should not run"}
    assert dispatch.respond("hi", classification, cache, registry) == LOW_CONFIDENCE_REPLY


def test_unknown_intent_returns_unknown_reply():
    cache = TelemetryCache()
    classification = {"intent": "no_such_intent", "confidence": 0.99}
    assert dispatch.respond("hi", classification, cache, {}) == UNKNOWN_INTENT_REPLY


def test_known_intent_calls_handler():
    captured = {}

    def fake_handler(command, cache, classification):
        captured["command"] = command
        captured["cache"] = cache
        captured["classification"] = classification
        return "handler-result"

    cache = TelemetryCache()
    classification = {"intent": "vitals_heart_rate", "confidence": 0.94}
    registry = {"vitals_heart_rate": fake_handler}

    result = dispatch.respond("what's my heart rate", classification, cache, registry)

    assert result == "handler-result"
    assert captured["command"] == "what's my heart rate"
    assert captured["cache"] is cache
    assert captured["classification"] is classification


def test_stale_cache_returns_unavailable():
    """The EVA heart_rate registry entry should hit the unavailable fallback when cache is empty."""
    from src.core.responder.registry_eva import REGISTRY_EVA

    cache = TelemetryCache(stale_after_s=10.0)
    result = REGISTRY_EVA["vitals_heart_rate"](
        "hi", cache, {"intent": "vitals_heart_rate", "confidence": 0.94}
    )
    assert result == TELEMETRY_UNAVAILABLE_REPLY


# --- Live-shape regression tests ------------------------------------------
# These payloads mirror what TTTDTT actually emits (captured 2026-05-11).
# If TSS changes shape, these break loudly instead of the demo failing live.


def test_registry_eva_heart_rate_reads_eva1():
    """Live-shape regression: telemetry.eva1.heart_rate is the canonical path.

    EVA's NN classifier emits `vitals_heart_rate`; the registry routes it to
    telemetry.eva1.<field>. The eva2 leg is unreachable from a single label
    (NN has no eva1/eva2 split — that distinction was a multilabel-era addition).
    """
    from src.core.responder.registry_eva import REGISTRY_EVA

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {
        "telemetry": {
            "eva1": {"heart_rate": 78.4},
            "eva2": {"heart_rate": 90.0},
        },
    })
    result = REGISTRY_EVA["vitals_heart_rate"](
        "hi", cache, {"intent": "vitals_heart_rate", "confidence": 0.9}
    )
    assert "78.4" in result and "heart rate" in result.lower()


def test_registry_pr_battery_level_reads_pr_telemetry():
    """Live-shape regression: pr_telemetry.primary_battery_level."""
    from src.core.responder.registry_pr import REGISTRY_PR

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 87.11}})
    result = REGISTRY_PR["Get_battery_level"](
        "hi", cache, {"intent": "Get_battery_level", "confidence": 0.9}
    )
    assert "87.1" in result


def test_registry_pr_oxygen_pressure_reads_pr_telemetry():
    """Live-shape regression: pr_telemetry.oxygen_pressure."""
    from src.core.responder.registry_pr import REGISTRY_PR

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"oxygen_pressure": 2185.18}})
    result = REGISTRY_PR["Get_oxygen_pressure"](
        "hi", cache, {"intent": "Get_oxygen_pressure", "confidence": 0.9}
    )
    assert "2185" in result


def test_handle_signal_strength_reads_signal_group():
    from src.core.responder.handlers_pr import handle_signal_strength

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv", {
        "signal": {"strength": -21.59, "ping_requested": 0, "ping_unlimited_requested": 0},
        "location": {"last_known_x": 0.0, "last_known_y": 0.0},
    })
    result = handle_signal_strength("hi", cache, {"intent": "get_signal_strength", "confidence": 0.9})
    assert "-21.6" in result


def test_handle_warnings_lists_active_errors():
    from src.core.responder.handlers_pr import handle_warnings

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv_errors", {
        "error_procedures": [
            {"code": "0000", "description": "Recovery Mode", "needs_resolved": True, "procedures": []},
        ],
    })
    result = handle_warnings("hi", cache, {"intent": "get_warnings", "confidence": 0.9})
    assert "Recovery Mode" in result


def test_handle_warnings_with_no_active_errors():
    from src.core.responder.handlers_pr import handle_warnings

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("ltv_errors", {"error_procedures": []})
    result = handle_warnings("hi", cache, {"intent": "get_warnings", "confidence": 0.9})
    assert result == "No active warnings."


# --- Phase 2: special-case PR handlers ------------------------------------

def test_handle_lidar_renders_vector_summary():
    from src.core.responder.handlers_pr import handle_lidar

    cache = TelemetryCache(stale_after_s=10.0)
    # Spec note: lidar is "list of 17 numbers" (intentPR.json)
    readings = [3.21, 4.50, -1.0, 0.0, 7.7, 8.8, 9.9, 10.1, 11.2,
                12.3, 13.4, 14.5, 15.6, 16.7, 17.8, 18.9, 20.0]
    cache.put("rover", {"pr_telemetry": {"lidar": readings}})
    result = handle_lidar("hi", cache, {"intent": "get_lidar", "confidence": 0.9})
    # We render the min/max as a summary rather than reading 17 numbers aloud.
    assert "lidar" in result.lower()
    assert "-1" in result or "minimum" in result.lower() or "min" in result.lower()


def test_handle_lidar_returns_unavailable_when_cache_empty():
    from src.core.responder.handlers_pr import handle_lidar

    cache = TelemetryCache(stale_after_s=10.0)
    result = handle_lidar("hi", cache, {"intent": "get_lidar", "confidence": 0.9})
    from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
    assert result == TELEMETRY_UNAVAILABLE_REPLY


def test_set_cabin_cooling_on_verbal_ack():
    from src.core.responder.handlers_pr import handle_set_cabin_cooling_on

    cache = TelemetryCache(stale_after_s=10.0)
    result = handle_set_cabin_cooling_on("turn cooling on", cache,
                                          {"intent": "set_cabin_cooling_on", "confidence": 0.9})
    assert "cabin cooling" in result.lower() and "on" in result.lower()


def test_set_lights_off_verbal_ack():
    from src.core.responder.handlers_pr import handle_set_lights_off

    cache = TelemetryCache(stale_after_s=10.0)
    result = handle_set_lights_off("kill the lights", cache,
                                    {"intent": "set_lights_off", "confidence": 0.9})
    assert "lights" in result.lower() and "off" in result.lower()


def test_all_six_set_handlers_exist_and_return_strings():
    """Quick coverage: every set_* intent has a callable that returns a non-empty string."""
    from src.core.responder import handlers_pr

    for name in [
        "handle_set_cabin_cooling_off",
        "handle_set_cabin_cooling_on",
        "handle_set_cabin_heating_off",
        "handle_set_cabin_heating_on",
        "handle_set_lights_off",
        "handle_set_lights_on",
    ]:
        fn = getattr(handlers_pr, name)
        cache = TelemetryCache(stale_after_s=10.0)
        out = fn("any", cache, {"intent": name.removeprefix("handle_"), "confidence": 0.9})
        assert isinstance(out, str) and out, name
