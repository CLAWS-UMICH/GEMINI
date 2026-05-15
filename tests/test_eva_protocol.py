import json

import pytest

from src.modes.eva.protocol import (
    FinalMsg,
    StartMsg,
    StopMsg,
    parse_incoming,
    serialize_final,
)


def test_parse_start_returns_start_msg():
    raw = json.dumps({"type": "start", "sample_rate": 16000, "channels": 1})
    msg = parse_incoming(raw)
    assert isinstance(msg, StartMsg)
    assert msg.sample_rate == 16000
    assert msg.channels == 1


def test_parse_stop_returns_stop_msg():
    msg = parse_incoming(json.dumps({"type": "stop"}))
    assert isinstance(msg, StopMsg)


def test_parse_malformed_json_returns_none():
    assert parse_incoming("not json") is None


def test_parse_missing_type_returns_none():
    assert parse_incoming(json.dumps({"sample_rate": 16000})) is None


def test_parse_unknown_type_returns_none():
    assert parse_incoming(json.dumps({"type": "wat"})) is None


def test_parse_start_missing_sample_rate_returns_none():
    assert parse_incoming(json.dumps({"type": "start", "channels": 1})) is None


def test_parse_start_missing_channels_returns_none():
    assert parse_incoming(json.dumps({"type": "start", "sample_rate": 16000})) is None


def test_parse_non_object_payload_returns_none():
    assert parse_incoming(json.dumps([1, 2, 3])) is None
    assert parse_incoming(json.dumps("hello")) is None


def test_serialize_final_omits_none_optional_fields():
    msg = FinalMsg(response="hi")
    data = json.loads(serialize_final(msg))
    assert data == {"type": "final", "response": "hi"}


def test_serialize_final_includes_present_fields():
    msg = FinalMsg(
        response="Heart rate 72.",
        transcript="check my vitals",
        intent="vitals_heart_rate",
        confidence=0.92,
        parameters={"NAVIGATION_TARGET_NAME": "ROVER"},
        latency_ms=187.0,
    )
    data = json.loads(serialize_final(msg))
    assert data == {
        "type": "final",
        "response": "Heart rate 72.",
        "transcript": "check my vitals",
        "intent": "vitals_heart_rate",
        "confidence": 0.92,
        "parameters": {"NAVIGATION_TARGET_NAME": "ROVER"},
        "latency_ms": 187.0,
    }


def test_serialize_final_preserves_empty_response():
    msg = FinalMsg(response="")
    data = json.loads(serialize_final(msg))
    assert data == {"type": "final", "response": ""}
