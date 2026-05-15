"""CORVUS Pressurized-Rover mode — standalone entry point.

Phase 1E: stdin-driven (type a command, get a printed response).
Phase 1F+: wake-word → VAD → Whisper STT → classify → Piper TTS.
"""

import asyncio
import logging
import sys

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.responder import dispatch
from src.core.responder.registry_pr import REGISTRY_PR
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient
from src.modes.eva.websocket_handler import log_error, log_info, log_success


async def stdin_loop(classifier, cache) -> None:
    """Read commands from stdin one line at a time. EOF or 'quit' exits."""
    log_info("Type a command and press Enter (or 'quit' to exit):")
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        command = line.strip()
        if not command:
            continue
        if command.lower() in ("quit", "exit", "q"):
            break
        classification = classifier.classify(command)
        response_text = dispatch.respond(command, classification, cache, REGISTRY_PR)
        print(f"[{classification['intent']} @ {classification['confidence']:.2f}] {response_text}")


async def start_agent() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log_info("Starting CORVUS-PR Agent...")
    log_info(f"Confidence threshold: {CONFIDENCE_THRESH_HIGH}")

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log_info(f"TTTDTT client started (target: {TTTDTT_URL})")

    classifier = build_classifier(mode="pr")
    log_success(f"Classifier loaded ({classifier.__class__.__name__})")

    try:
        await stdin_loop(classifier, cache)
    finally:
        await sio_client.stop()


def main() -> None:
    try:
        asyncio.run(start_agent())
    except KeyboardInterrupt:
        log_info("\nAgent stopped by user (Ctrl+C)")
    except Exception as exc:
        log_error(f"Agent crashed: {exc}")
        raise


if __name__ == "__main__":
    main()
