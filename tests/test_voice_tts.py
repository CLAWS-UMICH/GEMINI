import pytest

from src.voice.tts import DEFAULT_VOICE_PATH, PiperTTS


@pytest.fixture(scope="module")
def tts() -> PiperTTS:
    if not DEFAULT_VOICE_PATH.exists():
        pytest.skip(
            f"Piper voice missing at {DEFAULT_VOICE_PATH}; "
            f"run scripts/install_piper.sh first."
        )
    return PiperTTS()


def test_synthesize_returns_nonempty_audio(tts: PiperTTS):
    audio = tts.synthesize("hello world")
    assert audio.size > 0, "Expected non-empty audio buffer from Piper"
    assert audio.dtype.kind == "i", f"Expected int audio dtype, got {audio.dtype}"
