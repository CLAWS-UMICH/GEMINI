"""Multi-label intent classifier with per-mode label masking.

Spec: docs/superpowers/specs/2026-05-14-corvus-dual-mode-voice-and-model-swap-design.md §7

Construction:
  1. Load label2id.json (88 entries: intent_name → index).
  2. Load the active mode's catalog (intenteva.json for "eva", intentPR.json for "pr").
  3. Build an 88-dim float mask: 1.0 for indices belonging to this mode's intents,
     0.0 elsewhere.

classify(text):
  1. forward_texts([text]) → logits[1, 88]
  2. sigmoid(logits) → probs
  3. probs *= mask  (zero out the other mode's labels)
  4. argmax → idx
  5. return {"intent": id2label[idx], "confidence": float(probs[0, idx])}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import torch

from src.core.classifier.classifier_protocol import Classification
from src.core.classifier.multilabel_module import (
    MultilabelIntentModule,
    load_multilabel_module_for_inference,
)

log = logging.getLogger(__name__)

DEFAULT_CATALOGS_DIR = Path(__file__).resolve().parents[3] / "models" / "intent_catalogs"


class MultilabelClassifier:
    def __init__(
        self,
        multilabel_dir: Path,
        mode: Literal["eva", "pr"],
        catalogs_dir: Path | None = None,
        module: Any = None,
        device: torch.device | None = None,
    ) -> None:
        multilabel_dir = Path(multilabel_dir)
        label2id_path = multilabel_dir / "label2id.json"
        if not label2id_path.is_file():
            raise FileNotFoundError(f"label2id.json missing at {label2id_path}")

        label2id: dict[str, int] = json.loads(label2id_path.read_text())
        self._n_labels = len(label2id)
        # id2label as a flat list ordered by index, so argmax → name is O(1).
        self._id2label: list[str] = [""] * self._n_labels
        for name, idx in label2id.items():
            self._id2label[int(idx)] = str(name)

        catalogs_dir = catalogs_dir or DEFAULT_CATALOGS_DIR
        if mode == "pr":
            catalog_paths = [
                catalogs_dir / "intentPR.json",
                catalogs_dir / "intenteva.json",
            ]
        else:  # "eva" — unchanged
            catalog_paths = [catalogs_dir / "intenteva.json"]
        active_labels: set[str] = set()
        for path in catalog_paths:
            active_labels.update(row["intent"] for row in json.loads(Path(path).read_text()))

        unknown = active_labels - set(label2id)
        if unknown:
            raise ValueError(
                f"catalog labels missing from label2id: {sorted(unknown)[:5]}…"
            )

        self._device = device or torch.device("cpu")
        self._mode = mode

        # Mask as a float vector so we can multiply in-place after sigmoid.
        mask = torch.zeros(self._n_labels, dtype=torch.float32)
        for name in active_labels:
            mask[label2id[name]] = 1.0
        self._mask = mask.to(self._device)

        if module is None:
            module = load_multilabel_module_for_inference(
                checkpoint_path=multilabel_dir / "multilabel.pt",
                n_labels=self._n_labels,
                device=self._device,
                tokenizer_dir=multilabel_dir,
            )
        self._module = module

        log.info(
            "MultilabelClassifier ready: mode=%s, %d active labels of %d, device=%s",
            mode, int(mask.sum().item()), self._n_labels, self._device,
        )

    def classify(self, command: str) -> Classification:
        with torch.inference_mode():
            logits = self._module.forward_texts([command], self._device)
            probs = torch.sigmoid(logits) * self._mask  # [1, 88]
            idx = int(torch.argmax(probs, dim=1).item())
            confidence = float(probs[0, idx].item())
        return {
            "intent": self._id2label[idx],
            "confidence": confidence,
        }
