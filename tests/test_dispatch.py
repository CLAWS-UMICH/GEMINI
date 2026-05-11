import pytest

from src.responder import dispatch
from src.responder.fallback import (
    LOW_CONFIDENCE_REPLY,
    TELEMETRY_UNAVAILABLE_REPLY,
    UNKNOWN_INTENT_REPLY,
)
from src.telemetry.cache import TelemetryCache


def test_low_confidence_returns_low_conf_reply(monkeypatch):
    monkeypatch.setattr(dispatch, "REGISTRY", {"foo": lambda *_: "should not run"})
    cache = TelemetryCache()
    classification = {"intent": "foo", "confidence": 0.10}
    assert dispatch.respond("hi", classification, cache) == LOW_CONFIDENCE_REPLY


def test_unknown_intent_returns_unknown_reply(monkeypatch):
    monkeypatch.setattr(dispatch, "REGISTRY", {})
    cache = TelemetryCache()
    classification = {"intent": "no_such_intent", "confidence": 0.99}
    assert dispatch.respond("hi", classification, cache) == UNKNOWN_INTENT_REPLY


def test_known_intent_calls_handler(monkeypatch):
    captured = {}

    def fake_handler(command, cache, classification):
        captured["command"] = command
        captured["cache"] = cache
        captured["classification"] = classification
        return "handler-result"

    monkeypatch.setattr(dispatch, "REGISTRY", {"vitals_heart_rate": fake_handler})
    cache = TelemetryCache()
    classification = {"intent": "vitals_heart_rate", "confidence": 0.94}

    result = dispatch.respond("what's my heart rate", classification, cache)

    assert result == "handler-result"
    assert captured["command"] == "what's my heart rate"
    assert captured["cache"] is cache
    assert captured["classification"] is classification


def test_stale_cache_returns_unavailable():
    from src.responder.handlers import handle_heart_rate

    cache = TelemetryCache(stale_after_s=10.0)
    # never put anything → get("eva") returns None
    classification = {"intent": "vitals_heart_rate", "confidence": 0.94}
    assert handle_heart_rate("hi", cache, classification) == TELEMETRY_UNAVAILABLE_REPLY
