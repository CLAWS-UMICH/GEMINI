import time

import pytest

from src.core.telemetry.cache import TelemetryCache


def test_put_then_get_returns_payload():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"heart_bpm": 72})
    assert cache.get("eva") == {"heart_bpm": 72}


def test_get_unknown_channel_returns_none():
    cache = TelemetryCache(stale_after_s=10.0)
    assert cache.get("rover") is None


def test_stale_entry_returns_none(monkeypatch):
    cache = TelemetryCache(stale_after_s=10.0)
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    cache.put("eva", {"heart_bpm": 72})
    fake_now[0] = 1011.0  # 11 s later, past the 10 s window
    assert cache.get("eva") is None


def test_channels_are_independent():
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"heart_bpm": 72})
    cache.put("rover", {"battery_pct": 87})
    assert cache.get("eva") == {"heart_bpm": 72}
    assert cache.get("rover") == {"battery_pct": 87}
