"""Classifier factory.

Phase 1: returned NNClassifier (legacy MiniLM + 2-layer NN).
Phase 2 (active): when models/multilabel/label2id.json is present,
returns MultilabelClassifier with mode-aware label masking. Otherwise
falls back to NNClassifier and logs a warning.

See: docs/superpowers/specs/2026-05-14-corvus-dual-mode-voice-and-model-swap-design.md §7
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from src.config import BASE_DIR, NN_MODEL_PATH, TRAINING_DATA_PATH
from src.core.classifier.classifier_protocol import ClassifierProtocol
from src.core.classifier.nn_classifier import NNClassifier

log = logging.getLogger(__name__)

MODELS_DIR = BASE_DIR / "models"


def _build_multilabel(multilabel_dir: Path, mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    # Imported lazily so tests that exercise the NN fallback don't pay the
    # transformers import cost.
    from src.core.classifier.multilabel_classifier import MultilabelClassifier
    return MultilabelClassifier(multilabel_dir, mode=mode)


def build_classifier(mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    multilabel_dir = MODELS_DIR / "multilabel"
    if (multilabel_dir / "label2id.json").exists():
        log.info("multilabel sidecars present at %s; building MultilabelClassifier (mode=%s)",
                 multilabel_dir, mode)
        return _build_multilabel(multilabel_dir, mode)

    log.warning(
        "multi-label sidecars missing at %s; using legacy NN classifier (mode=%s)",
        multilabel_dir, mode,
    )
    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)
