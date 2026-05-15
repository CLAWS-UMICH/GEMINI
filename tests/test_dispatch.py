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
    from src.core.responder.handlers_eva import handle_heart_rate

    cache = TelemetryCache(stale_after_s=10.0)
    # never put anything → get("eva") returns None
    classification = {"intent": "vitals_heart_rate", "confidence": 0.94}
    assert handle_heart_rate("hi", cache, classification) == TELEMETRY_UNAVAILABLE_REPLY


# --- Live-shape regression tests ------------------------------------------
# These payloads mirror what TTTDTT actually emits (captured 2026-05-11).
# If TSS changes shape, these break loudly instead of the demo failing live.


def test_handle_heart_rate_reads_eva1():
    from src.core.responder.handlers_eva import handle_heart_rate

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {
        "telemetry": {
            "eva1": {"heart_rate": 78.4},
            "eva2": {"heart_rate": 90.0},
        },
    })
    result = handle_heart_rate("hi", cache, {"intent": "vitals_heart_rate", "confidence": 0.9})
    assert "78" in result and "beats per minute" in result


def test_handle_battery_level_reads_pr_telemetry():
    from src.core.responder.handlers_pr import handle_battery_level

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 87.11}})
    result = handle_battery_level("hi", cache, {"intent": "get_battery_level", "confidence": 0.9})
    assert "87.1" in result and "percent" in result


def test_handle_oxygen_pressure_reads_pr_telemetry():
    from src.core.responder.handlers_pr import handle_oxygen_pressure

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"oxygen_pressure": 2185.18}})
    result = handle_oxygen_pressure("hi", cache, {"intent": "get_oxygen_pressure", "confidence": 0.9})
    assert "2185" in result and "P S I" in result


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
