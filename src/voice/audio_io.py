"""sounddevice wrappers — capture and playback at 16 kHz mono.

Used only by PR mode. EVA mode receives audio over WebSocket and doesn't
need a local mic.

Importing this module fails on systems without the PortAudio shared library
(libportaudio2 on Debian/Ubuntu). PR mode handles that at boot.
"""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1


def record_blocking(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Block and capture `duration_s` seconds of mono float32 audio."""
    log.debug("Recording %.1fs of audio…", duration_s)
    audio = sd.rec(
        int(duration_s * sample_rate),
        samplerate=sample_rate,
        channels=CHANNELS,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def play_blocking(audio: np.ndarray, sample_rate: int) -> None:
    """Play int16 or float32 mono audio and wait for playback to finish."""
    log.debug("Playing %d samples at %d Hz", len(audio), sample_rate)
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


def open_input_stream(callback, sample_rate: int = SAMPLE_RATE, blocksize: int = 1280):
    """Open a continuous input stream; `callback(audio_chunk, frames, time_info, status)`
    is invoked per block. Used by wake-word and VAD for always-on listening.
    Default blocksize is 80ms at 16 kHz."""
    return sd.InputStream(
        samplerate=sample_rate,
        channels=CHANNELS,
        dtype="float32",
        blocksize=blocksize,
        callback=callback,
    )
