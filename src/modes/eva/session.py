"""EVA streaming session state machine.

See docs/superpowers/specs/2026-05-15-corvus-eva-unity-contract-design.md.
One EvaSession is constructed per WebSocket connection.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

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
