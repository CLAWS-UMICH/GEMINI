import asyncio
import logging

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient
from src.modes.eva.websocket_handler import (
    log_error,
    log_info,
    log_success,
    start_websocket,
)


async def start_server() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log_info("Starting CORVUS-EVA Server...")
    log_info(f"Confidence threshold: {CONFIDENCE_THRESH_HIGH}")

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log_info(f"TTTDTT client started (target: {TTTDTT_URL})")

    classifier = build_classifier(mode="eva")
    log_success(f"Classifier loaded ({classifier.__class__.__name__})")

    try:
        await start_websocket(classifier, cache, sio_client)
    finally:
        await sio_client.stop()


def main() -> None:
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        log_info("\nServer stopped by user (Ctrl+C)")
    except Exception as exc:
        log_error(f"Server crashed: {exc}")
        raise


if __name__ == "__main__":
    main()
