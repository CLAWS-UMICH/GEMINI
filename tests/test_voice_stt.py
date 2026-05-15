import numpy as np
import pytest

from src.voice.stt import DEFAULT_MODEL_DIR, WhisperSTT


@pytest.fixture(scope="module")
def stt() -> WhisperSTT:
    if not DEFAULT_MODEL_DIR.exists():
        pytest.skip(
            f"Whisper checkpoint missing at {DEFAULT_MODEL_DIR}; "
            f"run scripts/install_whisper.sh first."
        )
    return WhisperSTT()


def test_transcribe_silence_returns_empty_or_short(stt: WhisperSTT):
    """1 second of silence should not crash; output should be empty or trivially short."""
    silence = np.zeros(16000, dtype=np.float32)
    text = stt.transcribe(silence)
    assert len(text) < 30, f"Expected near-empty transcription for silence, got: {text!r}"
