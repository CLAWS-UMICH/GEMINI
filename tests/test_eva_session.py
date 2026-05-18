import json
import logging

import pytest

from src.modes.eva.protocol import StartMsg, StopMsg
from src.modes.eva.session import AudioReady, EvaSession, SessionState, MAX_BUFFER_BYTES, VAD_FRAME_SAMPLES


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


def _pcm_silence_bytes(samples: int) -> bytes:
    return (b"\x00\x00") * samples


def _pcm_nonzero_bytes(samples: int) -> bytes:
    # Arbitrary nonzero int16 LE samples. VAD verdict comes from FakeVAD sequence,
    # not actual content — we just need bytes of the right length.
    return b"\x10\x27" * samples  # 0x2710 = 10000


def test_binary_frame_in_idle_is_dropped():
    session = make_session()
    result = session.on_binary(_pcm_silence_bytes(1600))
    assert result is None
    assert session.state == SessionState.IDLE


def test_binary_frame_in_buffering_accumulates():
    session = make_session()
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    result = session.on_binary(_pcm_silence_bytes(1600))  # 100ms
    assert result is None
    assert session.state == SessionState.BUFFERING


def test_vad_is_called_in_512_sample_frames():
    vad = FakeVAD()
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    session.on_binary(_pcm_silence_bytes(1024))  # exactly 2 VAD frames
    assert vad.calls == 2


def test_end_of_speech_returns_audio_ready_and_returns_to_idle():
    # 1 speech frame, then 25 silence frames (> 22 hangover) -> end-of-speech
    sequence = [True] + [False] * 25
    vad = FakeVAD(sequence=sequence)
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    pcm = _pcm_nonzero_bytes(VAD_FRAME_SAMPLES * 26)
    result = session.on_binary(pcm)
    assert isinstance(result, AudioReady)
    assert session.state == SessionState.IDLE
    assert len(result.pcm) == len(pcm)


def test_no_speech_then_silence_does_not_end():
    # All silence frames; speech never starts; hangover should not fire
    vad = FakeVAD(sequence=[False] * 50)
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    pcm = _pcm_silence_bytes(VAD_FRAME_SAMPLES * 50)
    result = session.on_binary(pcm)
    assert result is None
    assert session.state == SessionState.BUFFERING


def test_buffer_cap_forces_end_of_speech():
    # Never speech, but buffer exceeds cap -> forced AudioReady
    vad = FakeVAD()
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    # Send slightly more than the cap in one go
    oversize = MAX_BUFFER_BYTES + 3200
    pcm = _pcm_silence_bytes(oversize // 2)
    result = session.on_binary(pcm)
    assert isinstance(result, AudioReady)
    assert session.state == SessionState.IDLE


def test_start_during_buffering_resets_but_stays_buffering():
    vad = FakeVAD()
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    session.on_binary(_pcm_silence_bytes(VAD_FRAME_SAMPLES * 4))
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    assert session.state == SessionState.BUFFERING
    assert vad.resets == 2


import asyncio


def _drive_to_audio_ready(session, vad: FakeVAD) -> AudioReady:
    vad.sequence = [True] + [False] * 25
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    pcm = _pcm_nonzero_bytes(VAD_FRAME_SAMPLES * 26)
    ready = session.on_binary(pcm)
    assert isinstance(ready, AudioReady)
    return ready


def test_finalize_emits_response_from_dispatch():
    vad = FakeVAD()
    stt = FakeSTT(transcript="check my heart rate")
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.95})

    def fake_handler(command, cache, classification):
        return "Heart rate is 72 BPM."

    registry = {"vitals_heart_rate": fake_handler}
    session = make_session(vad=vad, stt=stt, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.response == "Heart rate is 72 BPM."
    assert final.transcript == "check my heart rate"
    assert final.intent == "vitals_heart_rate"
    assert final.confidence == 0.95
    assert final.latency_ms is not None
    assert stt.calls == 1


def test_finalize_emits_voicestring_when_enabled(monkeypatch):
    monkeypatch.setenv("EMIT_VOICESTRING", "1")
    # Force config re-read
    from importlib import reload
    import src.config

    reload(src.config)

    vad = FakeVAD()
    sio = FakeSioClient()
    registry = {"vitals_heart_rate": lambda *a: "spoken text"}
    session = make_session(
        vad=vad,
        classifier=FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.9}),
        registry=registry,
        sio_client=sio,
    )
    ready = _drive_to_audio_ready(session, vad)
    asyncio.run(session.finalize(ready))

    assert sio.emissions == [("voiceString", "spoken text")]


def test_finalize_coerces_parameters_to_string_dict():
    vad = FakeVAD()
    classifier = FakeClassifier({
        "intent": "Set_navigation_target",
        "confidence": 0.9,
        "parameters": {"NAVIGATION_TARGET_NAME": 42},  # non-string value
    })
    registry = {"Set_navigation_target": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.parameters == {"NAVIGATION_TARGET_NAME": "42"}


def test_finalize_omits_parameters_when_empty():
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.9, "parameters": {}})
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.parameters is None


def test_finalize_marks_unhandled_when_below_confidence_threshold():
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.20})
    # Registry contains the intent; below-threshold still becomes "unhandled"
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.intent == "unhandled"


def test_finalize_marks_unhandled_when_intent_not_in_registry():
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "ghost_intent", "confidence": 0.99})
    session = make_session(vad=vad, classifier=classifier, registry={})
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.intent == "unhandled"


class RaisingSTT:
    def transcribe(self, audio):
        raise RuntimeError("whisper boom")


class RaisingClassifier:
    def classify(self, command):
        raise RuntimeError("classifier boom")


def test_finalize_whisper_failure_emits_empty_response():
    vad = FakeVAD()
    session = make_session(vad=vad, stt=RaisingSTT())
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.response == ""


def test_finalize_classifier_failure_emits_transcript_unhandled():
    vad = FakeVAD()
    stt = FakeSTT(transcript="say something")
    session = make_session(vad=vad, stt=stt, classifier=RaisingClassifier())
    ready = _drive_to_audio_ready(session, vad)

    final = asyncio.run(session.finalize(ready))

    assert final.response == "say something"
    assert final.transcript == "say something"
    assert final.intent == "unhandled"
    assert final.latency_ms is not None


def test_mic_event_emitted_on_start(caplog):
    session = make_session()
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))

    mic_records = [r for r in caplog.records if getattr(r, "event", None) == "mic"]
    assert len(mic_records) == 1
    assert "16000" in mic_records[0].getMessage()


def test_vad_event_emitted_on_end_of_speech(caplog):
    vad = FakeVAD(sequence=[True] + [False] * 25)
    session = make_session(vad=vad)
    session.on_text(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))
    pcm = _pcm_nonzero_bytes(VAD_FRAME_SAMPLES * 26)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        session.on_binary(pcm)

    vad_records = [r for r in caplog.records if getattr(r, "event", None) == "vad"]
    assert len(vad_records) == 1
    assert "s captured" in vad_records[0].getMessage()


def test_finalize_emits_stt_intent_reply_events(caplog):
    vad = FakeVAD()
    stt = FakeSTT(transcript="check heart rate")
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.95})
    registry = {"vitals_heart_rate": lambda *a: "HR is 72 bpm."}
    session = make_session(vad=vad, stt=stt, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    events = {getattr(r, "event", None): r for r in caplog.records}
    assert "stt" in events
    assert "check heart rate" in events["stt"].getMessage()
    assert "intent" in events
    assert "vitals_heart_rate" in events["intent"].getMessage()
    assert getattr(events["intent"], "intent_unhandled", False) is False
    assert "reply" in events
    assert "HR is 72 bpm." in events["reply"].getMessage()


def test_finalize_intent_event_flags_unhandled(caplog):
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.20})
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("INFO", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    intent_records = [r for r in caplog.records if getattr(r, "event", None) == "intent"]
    assert len(intent_records) == 1
    assert intent_records[0].intent_unhandled is True


def test_dropping_bytes_is_debug_not_info(caplog):
    session = make_session()
    with caplog.at_level("DEBUG", logger="src.modes.eva.session"):
        session.on_binary(_pcm_silence_bytes(1600))

    drop_records = [r for r in caplog.records if "dropping" in r.getMessage()]
    assert len(drop_records) == 1
    assert drop_records[0].levelno == logging.DEBUG


def test_latency_warning_is_debug(caplog, monkeypatch):
    monkeypatch.setattr("src.modes.eva.session.LATENCY_WARNING_MS", 0)
    vad = FakeVAD()
    classifier = FakeClassifier({"intent": "vitals_heart_rate", "confidence": 0.95})
    registry = {"vitals_heart_rate": lambda *a: "ok"}
    session = make_session(vad=vad, classifier=classifier, registry=registry)
    ready = _drive_to_audio_ready(session, vad)
    with caplog.at_level("DEBUG", logger="src.modes.eva.session"):
        asyncio.run(session.finalize(ready))

    latency_records = [r for r in caplog.records if "high latency" in r.getMessage()]
    assert len(latency_records) == 1
    assert latency_records[0].levelno == logging.DEBUG
