"""Tests for the EVA best-model multi-intent classifier.

Unit tests inject a stubbed module so they do not load the real checkpoint.
Real-bundle smoke tests are skipped when the bundle is not installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from src.config import CONFIDENCE_THRESH_HIGH
from src.core.classifier.multiintent_classifier import MultiIntentClassifier

BEST_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "best_model"
SIDECARS = [
    "multiintent.pt",
    "label2id.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
]


def _bundle_present() -> bool:
    return all((BEST_MODEL_DIR / name).exists() for name in SIDECARS)


@pytest.fixture
def fake_model_dir(tmp_path: Path) -> Path:
    labels = {
        "unhandled": 2,
        "vitals_heart_rate": 0,
        "open_menu_vitals": 1,
    }
    (tmp_path / "label2id.json").write_text(json.dumps(labels))
    return tmp_path


class _StubModule:
    def __init__(self, logits: torch.Tensor) -> None:
        self._logits = logits

    def forward_texts(self, texts: list[str], device: torch.device) -> torch.Tensor:
        return self._logits


def test_loads_label2id_and_orders_id2label(fake_model_dir: Path) -> None:
    logits = torch.tensor([[0.0, 4.0, 1.0]])
    clf = MultiIntentClassifier(
        fake_model_dir,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )

    result = clf.classify("open vitals")

    assert result["intent"] == "open_menu_vitals"


def test_high_logit_returns_backend_label_without_remapping(fake_model_dir: Path) -> None:
    logits = torch.tensor([[5.0, 0.0, 0.0]])
    clf = MultiIntentClassifier(
        fake_model_dir,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )

    result = clf.classify("what is my heart rate")

    assert result["intent"] == "vitals_heart_rate"


def test_unhandled_label_is_returned_without_remapping(fake_model_dir: Path) -> None:
    logits = torch.tensor([[0.0, 0.0, 5.0]])
    clf = MultiIntentClassifier(
        fake_model_dir,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )

    result = clf.classify("banana spaceship unrelated words")

    assert result["intent"] == "unhandled"


def test_classify_returns_float_confidence(fake_model_dir: Path) -> None:
    logits = torch.tensor([[2.0, 0.0, 0.0]])
    clf = MultiIntentClassifier(
        fake_model_dir,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )

    result = clf.classify("hi")

    assert isinstance(result["confidence"], float)


def test_missing_multiintent_checkpoint_raises_clear_error(tmp_path: Path) -> None:
    (tmp_path / "label2id.json").write_text(json.dumps({"vitals_heart_rate": 0}))

    with pytest.raises(FileNotFoundError, match="multiintent.pt"):
        MultiIntentClassifier(tmp_path)


def test_missing_label2id_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="label2id.json"):
        MultiIntentClassifier(
            tmp_path,
            module=_StubModule(torch.zeros(1, 1)),
            device=torch.device("cpu"),
        )


@pytest.mark.skipif(not _bundle_present(), reason="best_model bundle not installed")
def test_real_best_model_classifies_heart_rate() -> None:
    clf = MultiIntentClassifier(BEST_MODEL_DIR)
    result = clf.classify("what is my heart rate")

    assert result["intent"] == "vitals_heart_rate", result
    assert result["confidence"] >= 0.5


@pytest.mark.skipif(not _bundle_present(), reason="best_model bundle not installed")
def test_real_best_model_classifies_open_vitals() -> None:
    clf = MultiIntentClassifier(BEST_MODEL_DIR)
    result = clf.classify("open vitals")

    assert result["intent"] == "open_menu_vitals", result
    assert result["confidence"] >= 0.5


@pytest.mark.skipif(not _bundle_present(), reason="best_model bundle not installed")
def test_real_best_model_confidence_clears_backend_gate_for_heart_rate() -> None:
    clf = MultiIntentClassifier(BEST_MODEL_DIR)
    result = clf.classify("what is my heart rate")

    assert result["intent"] == "vitals_heart_rate", result
    assert result["confidence"] >= CONFIDENCE_THRESH_HIGH
