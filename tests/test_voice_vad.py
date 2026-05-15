import numpy as np
import pytest

from src.voice.vad import SileroVAD


@pytest.fixture(scope="module")
def vad():
    return SileroVAD()


def test_reset_returns_none_and_does_not_raise(vad):
    vad.reset()
    assert vad.reset() is None


def test_reset_allows_subsequent_is_speech_call(vad):
    silence = np.zeros(512, dtype=np.float32)
    vad.reset()
    result = vad.is_speech(silence)
    assert isinstance(result, bool)
    assert result is False
