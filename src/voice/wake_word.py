"""openWakeWord detector.

The Windows lock resolves to openwakeword 0.6.0, which (unlike 0.4.0) does
not ship the melspec/embedding preprocessor ONNX files in the wheel. We
bundle them in the repo at `models/openwakeword/` and pass explicit paths
to Model() so the wheel layout doesn't matter. The 0.4.0 vs 0.6.0 ONNX
files are interchangeable — same model architectures.

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

PREPROC_DIR = Path(__file__).resolve().parents[2] / "models" / "openwakeword"
MELSPEC_PATH = PREPROC_DIR / "melspectrogram.onnx"
EMBEDDING_PATH = PREPROC_DIR / "embedding_model.onnx"


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
        if not MELSPEC_PATH.is_file() or not EMBEDDING_PATH.is_file():
            raise FileNotFoundError(
                f"Preprocessor ONNX files missing under {PREPROC_DIR}. "
                f"Expected melspectrogram.onnx and embedding_model.onnx."
            )
        self._model = Model(
            wakeword_models=paths,
            melspec_model_path=str(MELSPEC_PATH),
            embedding_model_path=str(EMBEDDING_PATH),
        )
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
