"""Tests for MultilabelClassifier.

Two layers:
1. Mask-construction + classify-logic tests using a stubbed forward function
   (fast, no model download, runs on every CI invocation).
2. One integration test that loads the real bundle (skipped if any sidecar
   missing — keeps the suite green on machines without the bundle).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from src.core.classifier.multilabel_classifier import MultilabelClassifier

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MULTILABEL_DIR = MODELS_DIR / "PR-Model"
CATALOGS_DIR = MODELS_DIR / "intent_catalogs"
SIDECARS = ["multilabel.pt", "label2id.json", "tokenizer.json", "vocab.txt"]


def _bundle_present() -> bool:
    return (
        all((MULTILABEL_DIR / name).exists() for name in SIDECARS)
        and (CATALOGS_DIR / "intenteva.json").exists()
        and (CATALOGS_DIR / "intentPR.json").exists()
    )


@pytest.fixture
def fake_sidecar_dir(tmp_path) -> Path:
    """A multilabel/ dir with label2id.json only — used to exercise mask logic
    without loading the real model. The classifier accepts a `module` override
    in __init__ so we never touch the .pt."""
    labels = {
        "get_heart_rate_eva1": 0,
        "get_heart_rate_eva2": 1,
        "Get_battery_level": 2,
        "set_lights_on": 3,
    }
    (tmp_path / "label2id.json").write_text(json.dumps(labels))
    return tmp_path


@pytest.fixture
def fake_catalogs(tmp_path) -> Path:
    """models/intent_catalogs/ stub mapping to the labels above."""
    catalogs = tmp_path / "intent_catalogs"
    catalogs.mkdir()
    (catalogs / "intenteva.json").write_text(json.dumps([
        {"intent": "get_heart_rate_eva1", "description": ""},
        {"intent": "get_heart_rate_eva2", "description": ""},
    ]))
    (catalogs / "intentPR.json").write_text(json.dumps([
        {"intent": "Get_battery_level", "description": ""},
        {"intent": "set_lights_on", "description": ""},
    ]))
    return catalogs


class _StubModule:
    """Stand-in for MultilabelIntentModule that returns fixed logits."""

    def __init__(self, logits: torch.Tensor) -> None:
        self._logits = logits

    def forward_texts(self, texts: list[str], device: torch.device) -> torch.Tensor:
        return self._logits


def test_eva_mask_zeros_out_pr_labels(fake_sidecar_dir, fake_catalogs):
    # Logits favor a PR label (Get_battery_level=2) and an EVA label
    # (get_heart_rate_eva1=0). EVA mask should pick the EVA one.
    logits = torch.tensor([[1.0, 0.1, 5.0, 0.0]])  # PR (idx 2) has higher logit
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="eva",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    result = clf.classify("anything")
    assert result["intent"] == "get_heart_rate_eva1"
    # confidence = sigmoid(1.0) ≈ 0.731
    assert 0.7 < result["confidence"] < 0.74


def test_pr_mask_includes_eva_labels(fake_sidecar_dir, fake_catalogs):
    # Logits favor an EVA label (get_heart_rate_eva1=0). PR mode must NOT
    # zero it out anymore: PR sees both PR and EVA labels.
    logits = torch.tensor([[5.0, 0.1, 1.0, 0.5]])  # idx 0 (EVA) dominates
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="pr",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    result = clf.classify("anything")
    assert result["intent"] == "get_heart_rate_eva1"


def test_eva_mask_still_zeros_pr_labels(fake_sidecar_dir, fake_catalogs):
    logits = torch.tensor([[0.0, -1.0, 5.0, 0.0]])  # PR label (idx 2) dominates raw logits
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="eva",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    result = clf.classify("anything")
    # idx 0 (sigmoid 0.5) wins because idx 2 is masked to zero and idx 1
    # has a lower logit than idx 0 among EVA labels.
    assert result["intent"] == "get_heart_rate_eva1"


def test_classify_returns_classification_typed_dict_shape(fake_sidecar_dir, fake_catalogs):
    logits = torch.tensor([[0.0, 0.0, 2.0, 0.0]])
    clf = MultilabelClassifier(
        fake_sidecar_dir,
        mode="pr",
        catalogs_dir=fake_catalogs,
        module=_StubModule(logits),
        device=torch.device("cpu"),
    )
    out = clf.classify("hi")
    assert set(out.keys()) >= {"intent", "confidence"}
    assert isinstance(out["intent"], str)
    assert isinstance(out["confidence"], float)


def test_missing_label2id_raises(tmp_path, fake_catalogs):
    with pytest.raises(FileNotFoundError, match="label2id"):
        MultilabelClassifier(
            tmp_path,
            mode="eva",
            catalogs_dir=fake_catalogs,
            module=_StubModule(torch.zeros(1, 1)),
            device=torch.device("cpu"),
        )


# --- Integration test (loads the real bundle) -----------------------------

@pytest.mark.skipif(not _bundle_present(), reason="multilabel bundle not installed")
def test_real_bundle_classifies_canonical_heart_rate_to_eva1():
    """Smoke: 'what is eva 1 heart rate' should fire get_heart_rate_eva1."""
    clf = MultilabelClassifier(MULTILABEL_DIR, mode="eva")
    out = clf.classify("what is eva 1 heart rate")
    assert out["intent"] == "get_heart_rate_eva1", out
    assert out["confidence"] > 0.5


@pytest.mark.skipif(not _bundle_present(), reason="multilabel bundle not installed")
def test_real_bundle_classifies_canonical_battery_to_pr():
    clf = MultilabelClassifier(MULTILABEL_DIR, mode="pr")
    out = clf.classify("what's the rover battery level")
    # Either Get_battery_level or Get_primary_battery_level is acceptable
    assert out["intent"] in {"Get_battery_level", "Get_primary_battery_level"}, out
    assert out["confidence"] > 0.5


@pytest.mark.skipif(not _bundle_present(), reason="multilabel bundle not installed")
def test_real_bundle_eva_mode_never_returns_pr_intent():
    """Property: EVA mode must never return a label outside intenteva.json."""
    clf = MultilabelClassifier(MULTILABEL_DIR, mode="eva")
    pr_labels = {row["intent"] for row in json.load(open(MODELS_DIR / "intent_catalogs" / "intentPR.json"))}
    for utterance in [
        "rover speed",
        "turn the lights on",  # set_lights_on is PR
        "rover battery level",
    ]:
        out = clf.classify(utterance)
        assert out["intent"] not in pr_labels, (utterance, out)
