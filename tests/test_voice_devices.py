from unittest.mock import patch

from src.voice.devices import select_stt_device


def test_returns_cuda_float16_when_gpu_available():
    with patch("torch.cuda.is_available", return_value=True):
        device, compute_type = select_stt_device()
    assert device == "cuda"
    assert compute_type == "float16"


def test_returns_cpu_int8_when_gpu_unavailable():
    with patch("torch.cuda.is_available", return_value=False):
        device, compute_type = select_stt_device()
    assert device == "cpu"
    assert compute_type == "int8"
