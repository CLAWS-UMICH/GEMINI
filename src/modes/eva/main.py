import asyncio
import logging

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient
from src.modes.eva.log_format import configure_eva_logging
from src.modes.eva.websocket_handler import start_websocket
from src.voice.stt import DEFAULT_MODEL_DIR as WHISPER_MODEL_DIR, WhisperSTT
from src.voice.vad import SileroVAD

log = logging.getLogger(__name__)


async def start_server() -> None:
    configure_eva_logging()
    log.info("Starting CORVUS-EVA Server...")
    log.info("Confidence threshold: %s", CONFIDENCE_THRESH_HIGH)

    if not WHISPER_MODEL_DIR.exists():
        log.error(
            "Whisper checkpoint missing at %s. EVA mode requires Whisper for "
            "streaming PCM transcription. Run scripts/install_whisper.sh and retry.",
            WHISPER_MODEL_DIR,
        )
        raise SystemExit(1)

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log.info("TTTDTT client started (target: %s)", TTTDTT_URL)

    classifier = build_classifier(mode="eva")
    log.info("Classifier loaded (%s)", classifier.__class__.__name__)

    stt = WhisperSTT()
    log.info("Whisper STT loaded")

    vad = SileroVAD()
    log.info("Silero VAD loaded")

    try:
        await start_websocket(classifier, cache, sio_client, stt, vad, REGISTRY_EVA)
    finally:
        await sio_client.stop()


def main() -> None:
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        log.info("Server stopped by user (Ctrl+C)")
    except SystemExit:
        raise
    except Exception:
        log.exception("Server crashed")
        raise


if __name__ == "__main__":
    main()
