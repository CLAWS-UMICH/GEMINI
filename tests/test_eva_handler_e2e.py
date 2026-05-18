"""End-to-end smoke test for the EVA WS handler.

Skipped by default. To run:
    EVA_E2E=1 uv run python -m pytest tests/test_eva_handler_e2e.py -v

Requires the Whisper checkpoint to be present.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket

import numpy as np
import pytest
import websockets

from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.telemetry.cache import TelemetryCache
from src.modes.eva.session import VAD_FRAME_SAMPLES
from src.modes.eva.websocket_handler import _make_client_handler
from src.voice.stt import DEFAULT_MODEL_DIR as WHISPER_MODEL_DIR, WhisperSTT
from src.voice.vad import SileroVAD

pytestmark = pytest.mark.skipif(
    os.getenv("EVA_E2E") != "1",
    reason="set EVA_E2E=1 to run e2e smoke test (loads real Whisper + Silero)",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _synth_speech_pcm(seconds: float = 1.5) -> bytes:
    """A 200 Hz square-wave-ish burst followed by silence.

    Not real speech, but spectrally rich enough that Silero usually fires.
    If this test is flaky, replace with a recorded WAV under tests/data/.
    """
    sr = 16000
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    speech = (0.3 * np.sign(np.sin(2 * np.pi * 200 * t))).astype(np.float32)
    silence = np.zeros(sr, dtype=np.float32)  # 1s tail to trigger hangover
    samples = np.concatenate([speech, silence])
    pcm = (samples * 32767).astype(np.int16).tobytes()
    return pcm


async def _run_streaming_roundtrip() -> None:
    if not WHISPER_MODEL_DIR.exists():
        pytest.skip("Whisper checkpoint not installed")

    cache = TelemetryCache()

    class NullSio:
        async def emit(self, *_a, **_k):
            return None

    classifier_obj = type("C", (), {"classify": lambda self, c: {"intent": "unhandled", "confidence": 0.0}})()
    stt = WhisperSTT()
    vad = SileroVAD()

    handler = _make_client_handler(classifier_obj, cache, NullSio(), stt, vad, REGISTRY_EVA)
    port = _free_port()

    async with websockets.serve(handler, "127.0.0.1", port):
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps({"type": "start", "sample_rate": 16000, "channels": 1}))

            pcm = _synth_speech_pcm()
            # Ship in ~100ms chunks
            chunk = 3200
            for i in range(0, len(pcm), chunk):
                await ws.send(pcm[i : i + chunk])

            raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
            msg = json.loads(raw)
            assert msg["type"] == "final"
            assert "response" in msg


def test_full_streaming_roundtrip():
    asyncio.run(_run_streaming_roundtrip())


def test_websocket_handler_does_not_define_print_helpers():
    """Regression: the print()/ANSI log_* helpers and Colors class are gone.

    They were replaced by the logging-based path so EvaColorFormatter
    can render lifecycle messages consistently with turn events.
    """
    from src.modes.eva import websocket_handler

    assert not hasattr(websocket_handler, "Colors")
    assert not hasattr(websocket_handler, "log_info")
    assert not hasattr(websocket_handler, "log_success")
    assert not hasattr(websocket_handler, "log_warning")
    assert not hasattr(websocket_handler, "log_error")
    assert not hasattr(websocket_handler, "log_response")
