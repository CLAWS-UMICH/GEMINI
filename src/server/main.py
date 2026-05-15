import asyncio
import json
import logging

from src.core.classifier.nn_classifier import NNClassifier
from src.config import (
    CONFIDENCE_THRESH_HIGH,
    NN_MODEL_PATH,
    STALE_TELEMETRY_S,
    TRAINING_DATA_PATH,
    TTTDTT_URL,
)
from src.server.websocket_handler import log_error, log_info, log_success, start_websocket
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient


def _build_classifier() -> NNClassifier:
    with open(TRAINING_DATA_PATH) as f:
        data = json.load(f)
    labels = [intent["label"] for intent in data["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)


async def start_server() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_info("Starting CORVUS Server...")
    log_info(f"Confidence threshold: {CONFIDENCE_THRESH_HIGH}")

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log_info(f"TTTDTT client started (target: {TTTDTT_URL})")

    classifier = _build_classifier()
    log_success(f"Classifier loaded with {len(classifier.labels)} intents")

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
