import asyncio
import logging
import sys

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient
from src.modes.eva.websocket_handler import (
    log_error,
    log_info,
    log_success,
    log_warning,
    start_websocket,
)
from src.voice.stt import DEFAULT_MODEL_DIR as WHISPER_MODEL_DIR, WhisperSTT
from src.voice.vad import SileroVAD


async def start_server() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log_info("Starting CORVUS-EVA Server...")
    log_info(f"Confidence threshold: {CONFIDENCE_THRESH_HIGH}")

    if not WHISPER_MODEL_DIR.exists():
        log_error(
            f"Whisper checkpoint missing at {WHISPER_MODEL_DIR}. "
            f"EVA mode now requires Whisper for streaming PCM transcription. "
            f"Run scripts/install_whisper.sh and retry."
        )
        raise SystemExit(1)

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log_info(f"TTTDTT client started (target: {TTTDTT_URL})")

    classifier = build_classifier(mode="eva")
    log_success(f"Classifier loaded ({classifier.__class__.__name__})")

    stt = WhisperSTT()
    log_success("Whisper STT loaded")

    vad = SileroVAD()
    log_success("Silero VAD loaded")

    try:
        await start_websocket(classifier, cache, sio_client, stt, vad, REGISTRY_EVA)
    finally:
        await sio_client.stop()


def main() -> None:
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        log_info("\nServer stopped by user (Ctrl+C)")
    except SystemExit:
        raise
    except Exception as exc:
        log_error(f"Server crashed: {exc}")
        raise


if __name__ == "__main__":
    main()
