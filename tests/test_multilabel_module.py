"""Unit tests for the vendored MultilabelIntentModule wrapper.

These do NOT depend on the bundle being installed — we construct a tiny
in-memory module against the public MiniLM checkpoint to exercise the
shape contract. The integration test that loads the real checkpoint
lives in test_multilabel_classifier.py.
"""

from __future__ import annotations

import pytest
import torch


@pytest.fixture(scope="module")
def tiny_module():
    """Build a MultilabelIntentModule with the same encoder our embedder uses
    but a random-initialized head of size 3. Stays on CPU."""
    from src.core.classifier.multilabel_module import MultilabelIntentModule
    return MultilabelIntentModule("sentence-transformers/all-MiniLM-L6-v2", n_labels=3)


def test_mean_pool_shapes():
    from src.core.classifier.multilabel_module import mean_pool

    last_hidden = torch.randn(2, 5, 384)
    attention_mask = torch.tensor([[1, 1, 1, 0, 0], [1, 1, 1, 1, 1]])
    out = mean_pool(last_hidden, attention_mask)

    assert out.shape == (2, 384)
    # Row 0 mean is over the first 3 tokens (mask zeroes the rest)
    expected_row0 = last_hidden[0, :3, :].mean(dim=0)
    assert torch.allclose(out[0], expected_row0, atol=1e-6)


def test_forward_texts_returns_logits_with_right_shape(tiny_module):
    device = torch.device("cpu")
    tiny_module.to(device)
    tiny_module.eval()
    with torch.inference_mode():
        logits = tiny_module.forward_texts(["hello world", "what is my heart rate"], device)
    assert logits.shape == (2, 3)
    assert logits.dtype == torch.float32


def test_load_module_for_inference_round_trips(tmp_path, tiny_module):
    """Save the tiny module state in the teammate's checkpoint shape, then load it."""
    from src.core.classifier.multilabel_module import load_multilabel_module_for_inference

    ckpt = tmp_path / "multilabel.pt"
    torch.save(
        {
            "encoder_state_dict": tiny_module.encoder.state_dict(),
            "head_state_dict": tiny_module.head.state_dict(),
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        },
        ckpt,
    )

    loaded = load_multilabel_module_for_inference(
        checkpoint_path=ckpt,
        n_labels=3,
        device=torch.device("cpu"),
        tokenizer_dir=None,
    )
    with torch.inference_mode():
        logits = loaded.forward_texts(["hello"], torch.device("cpu"))
    assert logits.shape == (1, 3)
