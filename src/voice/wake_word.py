"""openWakeWord detector.

openwakeword 0.4.0 ships pretrained wake-word ONNX models bundled with the
package. Pass a wake-word name (e.g., 'hey_jarvis') to select one from the
bundle, or pass full paths via `model_paths` to load custom models.

Feed 80-ms audio chunks (1280 samples at 16 kHz) of float32 mono to
`process()`; returns True if any configured wake-word's score crosses the
threshold this chunk.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import openwakeword

log = logging.getLogger(__name__)

DEFAULT_WAKEWORD = ["hey_corvus", "corvus"]


def _resolve_wakeword_paths(names: list[str]) -> list[str]:
    """Map names like 'hey_jarvis' to bundled paths like '.../hey_jarvis_v0.1.onnx'."""
    bundled = openwakeword.get_pretrained_model_paths()
    resolved: list[str] = []
    for name in names:
        match = next(
            (p for p in bundled if Path(p).stem.startswith(name)),
            None,
        )
        if match is None:
            raise ValueError(
                f"Wake-word {name!r} not found in bundled models. "
                f"Available: {[Path(p).stem for p in bundled]}"
            )
        resolved.append(match)
    return resolved


class WakeWordDetector:
    def __init__(
        self,
        wakewords: list[str] | None = None,
        model_paths: list[str] | None = None,
        threshold: float = 0.5,
    ) -> None:
        from openwakeword.model import Model
        if model_paths is None:
            paths = _resolve_wakeword_paths(wakewords or DEFAULT_WAKEWORD)
        else:
            paths = model_paths
        log.info("Loading openWakeWord with %d model(s)", len(paths))
        self._model = Model(wakeword_model_paths=paths)
        self._threshold = threshold

    def process(self, audio_chunk: np.ndarray) -> bool:
        """audio_chunk: float32 or int16 mono 16 kHz. Returns True if any
        configured wake-word's score crossed the threshold this chunk."""
        # openwakeword expects int16 samples
        if audio_chunk.dtype != np.int16:
            audio_chunk = (audio_chunk * 32767.0).clip(-32768, 32767).astype(np.int16)
        scores = self._model.predict(audio_chunk)
        for _name, score in scores.items():
            if score >= self._threshold:
                return True
        return False
