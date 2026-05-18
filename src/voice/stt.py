"""Whisper STT wrapper around faster-whisper.

Device is selected at construction time via select_stt_device():
- GPU path: cuda + float16
- CPU path: cpu + int8

Pass a numpy float32 mono array sampled at 16kHz to transcribe().
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from src.voice.devices import select_stt_device

log = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "stt" / "whisper-medium.en"


class WhisperSTT:
    def __init__(self, model_dir: Path | None = None) -> None:
        model_path = model_dir or DEFAULT_MODEL_DIR
        if not model_path.exists():
            raise FileNotFoundError(
                f"Whisper checkpoint not found at {model_path}. "
                f"Run scripts/install_whisper.sh first."
            )
        device, compute_type = select_stt_device()
        log.info("Loading Whisper from %s (device=%s, compute_type=%s)",
                 model_path, device, compute_type)
        self._model = WhisperModel(str(model_path), device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32, mono, 16 kHz. Returns the concatenated text."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=5,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
