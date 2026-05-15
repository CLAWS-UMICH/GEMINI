"""Silero VAD wrapper.

Streaming voice-activity detection. Feed 32-ms frames (512 samples at 16 kHz)
of float32 mono audio; get back True/False for whether the frame contains
speech.
"""

from __future__ import annotations

import logging

import numpy as np
import torch

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class SileroVAD:
    def __init__(self) -> None:
        from silero_vad import load_silero_vad
        log.info("Loading Silero VAD…")
        self._model = load_silero_vad()
        self._model.reset_states()

    def is_speech(self, frame: np.ndarray, threshold: float = 0.5) -> bool:
        """frame: float32 mono, exactly 512 samples (32 ms at 16 kHz)."""
        tensor = torch.from_numpy(frame.astype(np.float32))
        prob = self._model(tensor, SAMPLE_RATE).item()
        return prob >= threshold

    def reset(self) -> None:
        """Reset Silero's internal LSTM state. Call at the start of each utterance."""
        self._model.reset_states()
