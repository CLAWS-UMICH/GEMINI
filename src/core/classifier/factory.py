"""Classifier factory.

Per-mode classifier selection:
- EVA mode: always NNClassifier (Unity contract vocabulary — `vitals_*`,
  `open_menu_*`, `Set_navigation_target`, etc.). The multilabel bundle's
  EVA1/EVA2-split labels do not match Unity's expectations.
- PR mode: MultilabelClassifier when models/multilabel/label2id.json is
  present; falls back to NNClassifier otherwise.

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


def _build_nn() -> ClassifierProtocol:
    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)


def build_classifier(mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    if mode == "eva":
        log.info("EVA mode: building NNClassifier (Unity-aligned vocabulary)")
        return _build_nn()

    multilabel_dir = MODELS_DIR / "multilabel"
    if (multilabel_dir / "label2id.json").exists():
        log.info("PR mode: multilabel sidecars present at %s; building MultilabelClassifier",
                 multilabel_dir)
        return _build_multilabel(multilabel_dir, mode)

    log.warning(
        "PR mode: multilabel sidecars missing at %s; falling back to NNClassifier",
        multilabel_dir,
    )
    return _build_nn()
