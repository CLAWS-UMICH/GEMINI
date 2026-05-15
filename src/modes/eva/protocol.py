"""Wire protocol for the EVA WebSocket contract with Unity.

See docs/superpowers/specs/2026-05-15-corvus-eva-unity-contract-design.md
and STT_UNITY_PYTHON_CONTRACT.md for the full contract.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Union


@dataclass(frozen=True)
class StartMsg:
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class StopMsg:
    pass


@dataclass(frozen=True)
class FinalMsg:
    response: str
    transcript: str | None = None
    intent: str | None = None
    confidence: float | None = None
    parameters: dict[str, str] | None = None
    latency_ms: float | None = None


IncomingMsg = Union[StartMsg, StopMsg]


def parse_incoming(text: str) -> IncomingMsg | None:
    """Parse a text frame from Unity. Returns None for any invalid input.

    Callers should drop None and log; never disconnect on parse failure.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    msg_type = data.get("type")
    if msg_type == "start":
        sample_rate = data.get("sample_rate")
        channels = data.get("channels")
        if not isinstance(sample_rate, int) or not isinstance(channels, int):
            return None
        return StartMsg(sample_rate=sample_rate, channels=channels)
    if msg_type == "stop":
        return StopMsg()
    return None


def serialize_final(msg: FinalMsg) -> str:
    """Serialize a FinalMsg, omitting any optional field that is None.

    The wire form always includes `type: "final"` and `response` (even if "").
    """
    payload: dict = {"type": "final", "response": msg.response}
    if msg.transcript is not None:
        payload["transcript"] = msg.transcript
    if msg.intent is not None:
        payload["intent"] = msg.intent
    if msg.confidence is not None:
        payload["confidence"] = msg.confidence
    if msg.parameters is not None:
        payload["parameters"] = msg.parameters
    if msg.latency_ms is not None:
        payload["latency_ms"] = msg.latency_ms
    return json.dumps(payload)
