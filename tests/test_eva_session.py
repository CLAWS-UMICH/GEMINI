import json

import pytest

from src.modes.eva.protocol import StartMsg, StopMsg
from src.modes.eva.session import EvaSession, SessionState


class FakeVAD:
    """Returns from a predetermined sequence; defaults to silence."""

    def __init__(self, sequence: list[bool] | None = None) -> None:
        self.sequence = list(sequence or [])
        self.calls = 0
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def is_speech(self, frame) -> bool:
        if self.calls < len(self.sequence):
            value = self.sequence[self.calls]
        else:
            value = False
        self.calls += 1
        return value


class FakeSTT:
    def __init__(self, transcript: str = "hello world") -> None:
        self.transcript = transcript
        self.calls = 0

    def transcribe(self, audio) -> str:
        self.calls += 1
        return self.transcript


class FakeClassifier:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or {"intent": "vitals_heart_rate", "confidence": 0.95}

    def classify(self, command):
        return dict(self.result)


class FakeSioClient:
    def __init__(self) -> None:
        self.emissions: list[tuple[str, object]] = []

    async def emit(self, event, data) -> None:
        self.emissions.append((event, data))


def make_session(
    vad=None,
    stt=None,
    classifier=None,
    registry=None,
    sio_client=None,
    cache=None,
):
    from src.core.telemetry.cache import TelemetryCache

    return EvaSession(
        vad=vad or FakeVAD(),
        stt=stt or FakeSTT(),
        classifier=classifier or FakeClassifier(),
        cache=cache or TelemetryCache(),
        sio_client=sio_client or FakeSioClient(),
        registry=registry if registry is not None else {},
    )


def test_session_starts_in_idle():
    session = make_session()
    assert session.state == SessionState.IDLE


def test_start_msg_transitions_to_buffering():
    session = make_session()
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    assert session.state == SessionState.BUFFERING


def test_start_msg_resets_vad():
    vad = FakeVAD()
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    assert vad.resets == 1


def test_stop_msg_in_idle_is_noop():
    session = make_session()
    session.on_text(json.dumps({"type": "stop"}))
    assert session.state == SessionState.IDLE


def test_stop_msg_in_buffering_returns_to_idle_without_final():
    session = make_session()
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    session.on_text(json.dumps({"type": "stop"}))
    assert session.state == SessionState.IDLE


def test_start_msg_with_wrong_sample_rate_stays_idle():
    session = make_session()
    session.on_text(json.dumps({"type": "start", "sample_rate": 48000, "channels": 1}))
    assert session.state == SessionState.IDLE


def test_start_msg_with_wrong_channels_stays_idle():
    session = make_session()
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 2}))
    assert session.state == SessionState.IDLE


def test_malformed_text_is_dropped_no_state_change():
    session = make_session()
    session.on_text("not json")
    assert session.state == SessionState.IDLE
