"""EVA streaming session state machine.

See docs/superpowers/specs/2026-05-15-corvus-eva-unity-contract-design.md.
One EvaSession is constructed per WebSocket connection.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from src.config import CONFIDENCE_THRESH_HIGH, EMIT_VOICESTRING, LATENCY_WARNING_MS
from src.core.responder import dispatch
from src.modes.eva.protocol import (
    FinalMsg,
    StartMsg,
    StopMsg,
    parse_incoming,
)

log = logging.getLogger(__name__)


def _hangover_frames() -> int:
    ms = float(os.getenv("EVA_VAD_HANGOVER_MS", "700"))
    return max(1, round(ms / 32))


def _max_buffer_bytes() -> int:
    seconds = float(os.getenv("EVA_MAX_UTTERANCE_S", "30"))
    return int(seconds * 16000 * 2)


HANGOVER_FRAMES = _hangover_frames()
MAX_BUFFER_BYTES = _max_buffer_bytes()
VAD_FRAME_SAMPLES = 512


class SessionState(Enum):
    IDLE = auto()
    BUFFERING = auto()


@dataclass(frozen=True)
class AudioReady:
    """Returned from on_binary when end-of-speech is decided."""

    pcm: bytes
    processing_start: float


class EvaSession:
    def __init__(
        self,
        *,
        vad,
        stt,
        classifier,
        cache,
        sio_client,
        registry: dict,
    ) -> None:
        self.vad = vad
        self.stt = stt
        self.classifier = classifier
        self.cache = cache
        self.sio_client = sio_client
        self.registry = registry

        self.state = SessionState.IDLE
        self._buffer = bytearray()
        self._unconsumed = np.empty(0, dtype=np.float32)
        self._speech_started = False
        self._hangover = 0

    def on_text(self, raw: str) -> None:
        msg = parse_incoming(raw)
        if msg is None:
            log.warning("eva: dropping malformed/unknown text frame")
            return
        if isinstance(msg, StartMsg):
            self._handle_start(msg)
        elif isinstance(msg, StopMsg):
            self._handle_stop()

    def _handle_start(self, msg: StartMsg) -> None:
        if msg.sample_rate != 16000 or msg.channels != 1:
            log.warning(
                "eva: rejecting start (sample_rate=%s channels=%s); v1 contract requires 16000/1",
                msg.sample_rate,
                msg.channels,
            )
            return
        self._reset_buffer()
        self.state = SessionState.BUFFERING
        log.info("eva: state IDLE -> BUFFERING")

    def _handle_stop(self) -> None:
        if self.state == SessionState.IDLE:
            return
        self._reset_buffer()
        self.state = SessionState.IDLE
        log.info("eva: state BUFFERING -> IDLE (stop received)")

    def _reset_buffer(self) -> None:
        self.vad.reset()
        self._buffer.clear()
        self._unconsumed = np.empty(0, dtype=np.float32)
        self._speech_started = False
        self._hangover = 0

    def on_binary(self, data: bytes) -> AudioReady | None:
        if self.state != SessionState.BUFFERING:
            log.info("eva: dropping %d bytes received in IDLE state", len(data))
            return None

        if len(data) % 2:
            log.warning("eva: odd-length PCM frame (%d bytes); dropping trailing byte", len(data))
            data = data[:-1]

        self._buffer.extend(data)

        # Decode the new bytes as int16 LE -> float32 in [-1, 1], queue for VAD
        new_samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if self._unconsumed.size:
            queue = np.concatenate([self._unconsumed, new_samples])
        else:
            queue = new_samples

        i = 0
        while queue.size - i >= VAD_FRAME_SAMPLES:
            frame = queue[i : i + VAD_FRAME_SAMPLES]
            i += VAD_FRAME_SAMPLES
            try:
                is_speech = self.vad.is_speech(frame)
            except Exception:
                log.exception("eva: VAD raised; forcing end-of-speech")
                self._unconsumed = queue[i:]
                return self._end_of_speech()

            if is_speech:
                self._speech_started = True
                self._hangover = 0
            elif self._speech_started:
                self._hangover += 1
                if self._hangover >= HANGOVER_FRAMES:
                    self._unconsumed = queue[i:]
                    return self._end_of_speech()

        self._unconsumed = queue[i:]

        if len(self._buffer) > MAX_BUFFER_BYTES:
            log.warning("eva: buffer cap %d bytes exceeded; forcing end-of-speech", MAX_BUFFER_BYTES)
            return self._end_of_speech()

        return None

    def _end_of_speech(self) -> AudioReady:
        pcm = bytes(self._buffer)
        ready = AudioReady(pcm=pcm, processing_start=time.monotonic())
        self.state = SessionState.IDLE
        log.info("eva: state BUFFERING -> IDLE (end-of-speech, %d bytes)", len(pcm))
        # Leave _buffer/_unconsumed populated until finalize completes; reset on next start.
        return ready

    async def finalize(self, ready: AudioReady) -> FinalMsg:
        try:
            audio = np.frombuffer(ready.pcm, dtype=np.int16).astype(np.float32) / 32768.0
            transcript = await asyncio.to_thread(self.stt.transcribe, audio)
        except Exception:
            log.exception("eva: STT failed; emitting empty final")
            return FinalMsg(response="")

        try:
            classification = self.classifier.classify(transcript)
        except Exception:
            log.exception("eva: classifier failed; emitting transcript-only final")
            latency_ms = round((time.monotonic() - ready.processing_start) * 1000, 2)
            return FinalMsg(
                response=transcript,
                transcript=transcript,
                intent="unhandled",
                latency_ms=latency_ms,
            )

        confidence = float(classification.get("confidence", 0.0))
        raw_intent = classification.get("intent", "unhandled")
        intent = raw_intent if (confidence >= CONFIDENCE_THRESH_HIGH and raw_intent in self.registry) else "unhandled"

        try:
            response_text = dispatch.respond(transcript, classification, self.cache, self.registry)
        except Exception:
            log.exception("eva: responder failed; emitting transcript-only final")
            response_text = transcript
            intent = "unhandled"

        raw_params = classification.get("parameters") or {}
        params: dict[str, str] | None = {k: str(v) for k, v in raw_params.items()} if raw_params else None

        latency_ms = round((time.monotonic() - ready.processing_start) * 1000, 2)
        if latency_ms > LATENCY_WARNING_MS:
            log.warning("eva: high latency %sms (threshold %sms)", latency_ms, LATENCY_WARNING_MS)

        if EMIT_VOICESTRING and self.sio_client is not None:
            try:
                await self.sio_client.emit("voiceString", response_text)
            except Exception:
                log.warning("eva: voiceString emit failed; continuing")

        log.info(
            "eva: final intent=%s confidence=%.3f latency_ms=%s transcript=%r",
            intent,
            confidence,
            latency_ms,
            transcript,
        )
        return FinalMsg(
            response=response_text,
            transcript=transcript,
            intent=intent,
            confidence=confidence,
            parameters=params,
            latency_ms=latency_ms,
        )
