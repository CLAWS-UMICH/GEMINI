"""CORVUS Pressurized-Rover mode — standalone audio loop.

Flow: wake-word → VAD-gated capture → Whisper STT → classify → Piper TTS.
`--text` swaps the front-end for stdin input (skips wake-word/VAD/STT);
Piper still speaks the response in both modes.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np

from src.config import (
    CONFIDENCE_THRESH_HIGH,
    STALE_TELEMETRY_S,
    TTTDTT_URL,
)
from src.core.classifier.factory import build_classifier
from src.core.log_format import CYAN, DIM_GREY, GREEN, MAGENTA, YELLOW, configure_logging
from src.core.responder import dispatch
from src.core.responder.registry_pr import REGISTRY_PR_FULL
from src.core.telemetry.cache import TelemetryCache
from src.core.telemetry.client import TelemetryClient

VAD_FRAME_SAMPLES = 512        # ~32 ms at 16 kHz (Silero requirement)
WAKEWORD_BLOCK_SAMPLES = 1280  # ~80 ms at 16 kHz (openWakeWord requirement)
SAMPLE_RATE = 16000
SILENCE_FRAMES_TO_END = 25     # ~800 ms of silence terminates capture
MAX_CAPTURE_S = 8.0

WAKE_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "wake_word" / "hey_corvus.onnx"

log = logging.getLogger(__name__)

PR_EVENT_TAGS = {
    "wake":   "[WAKE]   ",
    "vad":    "[VAD]    ",
    "stt":    "[STT]    ",
    "intent": "[INTENT] ",
    "reply":  "[REPLY]  ",
    "tts":    "[TTS]    ",
}
PR_EVENT_COLORS = {
    "wake":   CYAN,
    "vad":    DIM_GREY,
    "stt":    GREEN,
    "intent": YELLOW,
    "reply":  MAGENTA,
    "tts":    DIM_GREY,
}


async def capture_utterance(queue: asyncio.Queue, vad) -> np.ndarray:
    """Pull mic chunks from the shared stream's queue, re-block into 512-sample
    VAD frames, and terminate after SILENCE_FRAMES_TO_END consecutive silent
    frames (or MAX_CAPTURE_S total). Sharing one stream avoids the input-overflow
    that came from opening a fresh sd.rec() per VAD frame while the wake-word
    stream was still open."""
    buffer: list[np.ndarray] = []
    vad_carry = np.zeros(0, dtype=np.float32)
    silent_frames = 0
    frames_processed = 0
    max_frames = int((MAX_CAPTURE_S * SAMPLE_RATE) // VAD_FRAME_SAMPLES)
    vad.reset()

    while frames_processed < max_frames:
        chunk = await queue.get()
        buffer.append(chunk)
        vad_carry = np.concatenate([vad_carry, chunk])
        while len(vad_carry) >= VAD_FRAME_SAMPLES:
            frame = vad_carry[:VAD_FRAME_SAMPLES]
            vad_carry = vad_carry[VAD_FRAME_SAMPLES:]
            if vad.is_speech(frame):
                silent_frames = 0
            else:
                silent_frames += 1
            frames_processed += 1
            if (
                silent_frames >= SILENCE_FRAMES_TO_END
                and frames_processed > SILENCE_FRAMES_TO_END
            ):
                return np.concatenate(buffer)
    return np.concatenate(buffer) if buffer else np.zeros(0, dtype=np.float32)


async def voice_loop(classifier, cache, stt, tts, vad, wake) -> None:
    from src.voice.audio_io import open_input_stream, play_blocking

    log.info("Wake word listener active. Say 'hey corvus' to interact.")
    wake_triggered = asyncio.Event()
    main_loop = asyncio.get_event_loop()
    capture_queue: asyncio.Queue = asyncio.Queue()
    state = {"mode": "wake"}  # 'wake' | 'capture' — read by sounddevice thread

    def callback(indata, frames, time_info, status):
        if status:
            log.warning("Audio status: %s", status)
        chunk = (indata[:, 0] if indata.ndim > 1 else indata).astype(np.float32, copy=True)
        if state["mode"] == "wake":
            if wake.process(chunk):
                main_loop.call_soon_threadsafe(wake_triggered.set)
        else:
            main_loop.call_soon_threadsafe(capture_queue.put_nowait, chunk)

    with open_input_stream(callback, blocksize=WAKEWORD_BLOCK_SAMPLES):
        while True:
            await wake_triggered.wait()
            wake_triggered.clear()
            log.info("detected", extra={"event": "wake"})
            log.info("capturing…", extra={"event": "vad"})

            while not capture_queue.empty():
                capture_queue.get_nowait()
            state["mode"] = "capture"
            try:
                audio = await capture_utterance(capture_queue, vad)
            finally:
                state["mode"] = "wake"

            command = await main_loop.run_in_executor(None, lambda: stt.transcribe(audio))
            log.info("%r", command, extra={"event": "stt"})

            if not command:
                continue
            classification = classifier.classify(command)
            response_text = dispatch.respond(command, classification, cache, REGISTRY_PR_FULL)
            log.info(
                "%s (conf %.2f)",
                classification["intent"],
                classification["confidence"],
                extra={"event": "intent"},
            )
            log.info("%s", response_text, extra={"event": "reply"})

            audio_out = await main_loop.run_in_executor(None, lambda: tts.synthesize(response_text))
            await main_loop.run_in_executor(None, lambda: play_blocking(audio_out, tts.sample_rate))


async def text_loop(classifier, cache, tts) -> None:
    from src.voice.audio_io import play_blocking

    log.info("Type a command and press Enter (or 'quit' to exit):")
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
        response_text = dispatch.respond(command, classification, cache, REGISTRY_PR_FULL)
        log.info("%r", command, extra={"event": "stt"})
        log.info(
            "%s (conf %.2f)",
            classification["intent"],
            classification["confidence"],
            extra={"event": "intent"},
        )
        log.info("%s", response_text, extra={"event": "reply"})
        audio_out = await loop.run_in_executor(None, lambda: tts.synthesize(response_text))
        await loop.run_in_executor(None, lambda: play_blocking(audio_out, tts.sample_rate))


async def start_agent(text_mode: bool) -> None:
    configure_logging(
        event_tags=PR_EVENT_TAGS,
        event_colors=PR_EVENT_COLORS,
        level_env_var="PR_LOG_LEVEL",
    )
    log.info("Starting CORVUS-PR Agent…")
    log.info("Confidence threshold: %s", CONFIDENCE_THRESH_HIGH)
    log.info("Mode: %s", "text" if text_mode else "voice")

    cache = TelemetryCache(stale_after_s=STALE_TELEMETRY_S)
    sio_client = TelemetryClient(TTTDTT_URL, cache)
    sio_client.start()
    log.info("TTTDTT client started (target: %s)", TTTDTT_URL)

    classifier = build_classifier(mode="pr")
    log.info("Classifier loaded (%s)", classifier.__class__.__name__)

    from src.voice.tts import PiperTTS
    tts = PiperTTS()
    log.info("Piper TTS loaded")

    try:
        if text_mode:
            await text_loop(classifier, cache, tts)
        else:
            from src.voice.stt import WhisperSTT
            from src.voice.vad import SileroVAD
            from src.voice.wake_word import WakeWordDetector
            stt = WhisperSTT()
            log.info("Whisper STT loaded")
            vad = SileroVAD()
            log.info("Silero VAD loaded")
            wake = WakeWordDetector(model_paths=[str(WAKE_MODEL_PATH)])
            log.info("openWakeWord loaded")
            await voice_loop(classifier, cache, stt, tts, vad, wake)
    finally:
        await sio_client.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--text",
        action="store_true",
        help="Type commands instead of speaking; Piper still responds. Useful for rapid model testing.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(start_agent(text_mode=args.text))
    except KeyboardInterrupt:
        log.info("Agent stopped by user (Ctrl+C)")
    except Exception:
        log.exception("Agent crashed")
        raise


if __name__ == "__main__":
    main()
