"""openWakeWord detector.

uv.lock resolves to openwakeword 0.6.0 on Windows and 0.4.0 on Linux
(0.6.0 hard-requires tflite-runtime which has no Python 3.13 wheels on
Linux). The two versions ship incompatible ``Model.__init__`` kwarg
names: 0.6.0 uses ``wakeword_models`` / ``melspec_model_path`` /
``embedding_model_path``; 0.4.0 uses ``wakeword_model_paths`` and bundles
its own preprocessor ONNX. ``_build_model`` introspects the signature so
the same call site works on both. The bundled-vs-repo preprocessor ONNX
files at ``models/openwakeword/`` are interchangeable with 0.6.0's.

Feed 80-ms audio chunks (1280 samples at 16 kHz) of float32 mono to
``process()``; returns True if any configured wake-word's score crosses
the threshold this chunk.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path

import numpy as np
import openwakeword

log = logging.getLogger(__name__)

DEFAULT_WAKEWORD = ["hey_corvus", "corvus"]

PREPROC_DIR = Path(__file__).resolve().parents[2] / "models" / "openwakeword"
MELSPEC_PATH = PREPROC_DIR / "melspectrogram.onnx"
EMBEDDING_PATH = PREPROC_DIR / "embedding_model.onnx"


def _build_model(paths: list[str]):
    from openwakeword.model import Model
    params = inspect.signature(Model.__init__).parameters
    if "wakeword_models" in params:
        if not MELSPEC_PATH.is_file() or not EMBEDDING_PATH.is_file():
            raise FileNotFoundError(
                f"Preprocessor ONNX files missing under {PREPROC_DIR}. "
                f"Expected melspectrogram.onnx and embedding_model.onnx."
            )
        return Model(
            wakeword_models=paths,
            melspec_model_path=str(MELSPEC_PATH),
            embedding_model_path=str(EMBEDDING_PATH),
        )
    return Model(wakeword_model_paths=paths)


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
        if model_paths is None:
            paths = _resolve_wakeword_paths(wakewords or DEFAULT_WAKEWORD)
        else:
            paths = model_paths
        log.info("Loading openWakeWord with %d model(s)", len(paths))
        self._paths = paths
        self._threshold = threshold
        self._model = _build_model(paths)

    def process(self, audio_chunk: np.ndarray) -> bool:
        """audio_chunk: float32 or int16 mono 16 kHz. Returns True if any
        configured wake-word's score crossed the threshold this chunk."""
        triggered, _score = self.process_with_score(audio_chunk)
        return triggered

    def process_with_score(self, audio_chunk: np.ndarray) -> tuple[bool, float]:
        """audio_chunk: float32 or int16 mono 16 kHz. Returns
        (triggered, max_score) so callers can log the fire score."""
        if audio_chunk.dtype != np.int16:
            audio_chunk = (audio_chunk * 32767.0).clip(-32768, 32767).astype(np.int16)
        scores = self._model.predict(audio_chunk)
        max_score = max(scores.values()) if scores else 0.0
        return (max_score >= self._threshold, float(max_score))

    def reset(self) -> None:
        """Wipe openWakeWord's internal rolling buffer so a fresh utterance
        doesn't activate against stale audio."""
        reset_fn = getattr(self._model, "reset", None) or getattr(self._model, "reset_states", None)
        if callable(reset_fn):
            reset_fn()
            return
        # Fallback: re-instantiate the model with cached paths. Slower
        # (~100 ms) but always correct.
        self._model = _build_model(self._paths)
