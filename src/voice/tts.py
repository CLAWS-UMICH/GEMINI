"""Piper TTS wrapper. CPU-only by design (Piper ships optimized for CPU).

Piper 1.4.x API used here:
- PiperVoice.load(model_path) returns a voice; voice.config.sample_rate is the
  output rate
- voice.synthesize(text) yields AudioChunk objects; each chunk exposes
  audio_int16_array (numpy int16 mono)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_VOICE_PATH = (
    Path(__file__).resolve().parents[2] / "models" / "tts" / "piper" / "en_US-lessac-medium.onnx"
)


class PiperTTS:
    def __init__(self, voice_path: Path | None = None) -> None:
        from piper import PiperVoice
        voice = voice_path or DEFAULT_VOICE_PATH
        if not voice.exists():
            raise FileNotFoundError(
                f"Piper voice not found at {voice}. Run scripts/install_piper.sh first."
            )
        log.info("Loading Piper voice from %s", voice)
        self._voice = PiperVoice.load(str(voice))
        self.sample_rate = self._voice.config.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        """Returns int16 mono audio at self.sample_rate Hz."""
        chunks: list[np.ndarray] = []
        for chunk in self._voice.synthesize(text):
            chunks.append(np.asarray(chunk.audio_int16_array, dtype=np.int16))
        if not chunks:
            return np.array([], dtype=np.int16)
        return np.concatenate(chunks)
