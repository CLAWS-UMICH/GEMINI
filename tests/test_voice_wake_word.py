"""Smoke tests for WakeWordDetector. The actual openWakeWord Model is
loaded once and we exercise reset() + process_with_score() against it.
"""

from pathlib import Path

import numpy as np
import pytest

WAKE_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "wake_word" / "hey_corvus.onnx"
MELSPEC_PATH = Path(__file__).resolve().parents[1] / "models" / "openwakeword" / "melspectrogram.onnx"


def _wake_assets_present() -> bool:
    return WAKE_MODEL_PATH.exists() and MELSPEC_PATH.exists()


requires_wake_assets = pytest.mark.skipif(
    not _wake_assets_present(),
    reason="wake-word ONNX assets not installed",
)


@pytest.fixture
def detector():
    from src.voice.wake_word import WakeWordDetector
    return WakeWordDetector(model_paths=[str(WAKE_MODEL_PATH)])


@requires_wake_assets
def test_reset_is_callable_without_raising(detector):
    detector.reset()  # idempotent + must not throw


@requires_wake_assets
def test_process_with_score_returns_tuple(detector):
    silence = np.zeros(1280, dtype=np.float32)
    triggered, score = detector.process_with_score(silence)
    assert isinstance(triggered, bool)
    assert isinstance(score, float)
    # Silence should not trigger; score is some real number, possibly small.
    assert not triggered


@requires_wake_assets
def test_process_with_score_int16_input_accepted(detector):
    silence = np.zeros(1280, dtype=np.int16)
    triggered, score = detector.process_with_score(silence)
    assert isinstance(triggered, bool)
    assert isinstance(score, float)


@requires_wake_assets
def test_process_back_compat_returns_bool(detector):
    silence = np.zeros(1280, dtype=np.float32)
    triggered = detector.process(silence)
    assert isinstance(triggered, bool)
