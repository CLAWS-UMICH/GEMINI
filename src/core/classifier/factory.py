"""Classifier factory.

Per-mode classifier selection:
- EVA mode: MultiIntentClassifier when the models/best_model bundle is
  present; falls back to NNClassifier otherwise.
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

log = logging.getLogger(__name__)

MODELS_DIR = BASE_DIR / "models"
BEST_MODEL_DIR = MODELS_DIR / "best_model"
BEST_MODEL_REQUIRED_FILES = (
    "multiintent.pt",
    "label2id.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
)


def _build_multilabel(multilabel_dir: Path, mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    # Imported lazily so tests that exercise the NN fallback don't pay the
    # transformers import cost.
    from src.core.classifier.multilabel_classifier import MultilabelClassifier
    return MultilabelClassifier(multilabel_dir, mode=mode)


def _build_multiintent(best_model_dir: Path) -> ClassifierProtocol:
    # Imported lazily so PR mode and fallback tests don't pay the transformers
    # import cost.
    from src.core.classifier.multiintent_classifier import MultiIntentClassifier
    return MultiIntentClassifier(best_model_dir)


def _build_nn() -> ClassifierProtocol:
    from src.core.classifier.nn_classifier import NNClassifier

    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)


def _best_model_bundle_present(best_model_dir: Path) -> bool:
    return all((best_model_dir / name).is_file() for name in BEST_MODEL_REQUIRED_FILES)


def build_classifier(mode: Literal["eva", "pr"]) -> ClassifierProtocol:
    if mode == "eva":
        if _best_model_bundle_present(BEST_MODEL_DIR):
            log.info(
                "EVA mode: best_model bundle present at %s; building MultiIntentClassifier",
                BEST_MODEL_DIR,
            )
            return _build_multiintent(BEST_MODEL_DIR)
        log.warning(
            "EVA mode: best_model bundle missing at %s; falling back to NNClassifier",
            BEST_MODEL_DIR,
        )
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
