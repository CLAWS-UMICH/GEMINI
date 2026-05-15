"""Device routing for the voice stack.

Single decision point for which device runs Whisper STT. Everything else
(classifier, TTS, VAD, wake-word) stays on CPU by design — see spec §5.

Boot log captures the chosen device verbatim so any session log is
self-explanatory.
"""

from __future__ import annotations

import logging

import torch

log = logging.getLogger(__name__)


def select_stt_device() -> tuple[str, str]:
    """Returns (device, compute_type) for faster-whisper.

    GPU path: cuda + float16. CPU path: cpu + int8.
    """
    if torch.cuda.is_available():
        log.info("STT device: cuda (compute_type=float16)")
        return ("cuda", "float16")
    log.warning(
        "CUDA not available; STT falling back to CPU (compute_type=int8)"
    )
    return ("cpu", "int8")
