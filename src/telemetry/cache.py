import time
from threading import Lock
from typing import Any


class TelemetryCache:
    def __init__(self, stale_after_s: float = 10.0) -> None:
        self._lock = Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self._timestamps: dict[str, float] = {}
        self._stale_after_s = stale_after_s

    def put(self, channel: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._data[channel] = payload
            self._timestamps[channel] = time.monotonic()

    def get(self, channel: str) -> dict[str, Any] | None:
        with self._lock:
            ts = self._timestamps.get(channel)
            if ts is None or (time.monotonic() - ts) > self._stale_after_s:
                return None
            return self._data[channel]
