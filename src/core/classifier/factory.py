"""Classifier factory.

Phase 1: always returns NNClassifier (the legacy MiniLM + 2-layer NN model).
Phase 2: when models/multilabel/label2id.json is present, returns
MultilabelClassifier with mode-aware label masking.

See: docs/superpowers/specs/2026-05-14-corvus-dual-mode-voice-and-model-swap-design.md §7
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from src.config import BASE_DIR, NN_MODEL_PATH, TRAINING_DATA_PATH
from src.core.classifier.classifier_protocol import ClassifierProtocol
from src.core.classifier.nn_classifier import NNClassifier

log = logging.getLogger(__name__)

MODELS_DIR = BASE_DIR / "models"


def build_classifier(mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    multilabel_sidecar = MODELS_DIR / "multilabel" / "label2id.json"
    if multilabel_sidecar.exists():
        raise NotImplementedError(
            "multi-label classifier path not implemented yet; "
            "this lands in Phase 2 once the teammate's sidecar artifacts arrive"
        )
    log.warning(
        "multi-label sidecars missing at %s; using legacy NN classifier (mode=%s)",
        multilabel_sidecar,
        mode,
    )
    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)
