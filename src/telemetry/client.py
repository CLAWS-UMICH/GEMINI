import asyncio
import logging

import socketio

from src.telemetry.cache import TelemetryCache

logger = logging.getLogger(__name__)

EVENT_TO_CHANNEL = {
    "eva-telemetry": "eva",
    "rover-telemetry": "rover",
    "ltv-telemetry": "ltv",
    "ltv-errors-telemetry": "ltv_errors",
}


class TelemetryClient:
    """Async Socket.IO client that mirrors TTTDTT telemetry events into a cache."""

    def __init__(self, url: str, cache: TelemetryCache) -> None:
        self._url = url
        self._cache = cache
        self._sio = socketio.AsyncClient(reconnection=True, reconnection_attempts=0)
        self._task: asyncio.Task | None = None

        for event, channel in EVENT_TO_CHANNEL.items():
            self._sio.on(event, self._make_handler(channel))

        @self._sio.event
        async def connect() -> None:
            logger.info("TTTDTT connected: %s", self._url)

        @self._sio.event
        async def disconnect() -> None:
            logger.warning("TTTDTT disconnected: %s", self._url)

    def _make_handler(self, channel: str):
        async def handler(payload):
            self._cache.put(channel, payload)
        return handler

    @property
    def connected(self) -> bool:
        return self._sio.connected

    async def emit(self, event: str, data) -> None:
        if not self._sio.connected:
            return
        try:
            await self._sio.emit(event, data)
        except Exception as exc:  # noqa: BLE001 — emit failures must not break the WS path
            logger.warning("TTTDTT emit %s failed: %s", event, exc)

    async def _run(self) -> None:
        while True:
            try:
                await self._sio.connect(self._url)
                await self._sio.wait()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("TTTDTT connect error: %s; retrying in 5s", exc)
            await asyncio.sleep(5.0)

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self._run(), name="telemetry-client")
        return self._task

    async def stop(self) -> None:
        if self._sio.connected:
            try:
                await self._sio.disconnect()
            except Exception:  # noqa: BLE001
                pass
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
