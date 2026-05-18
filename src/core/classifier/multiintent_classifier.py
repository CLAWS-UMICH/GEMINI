"""EVA multi-intent classifier backed by models/best_model/multiintent.pt."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from src.core.classifier.classifier_protocol import Classification
from src.core.classifier.multilabel_module import mean_pool

log = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_MAX_LENGTH = 128


class MultiIntentModule(nn.Module):
    def __init__(self, model_name: str, n_labels: int, max_length: int) -> None:
        super().__init__()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.encoder = AutoModel.from_pretrained(model_name)
        self.max_length = max_length
        hidden_size = int(self.encoder.config.hidden_size)
        self.head = nn.Linear(hidden_size, n_labels)

    def forward_texts(self, texts: list[str], device: torch.device) -> torch.Tensor:
        enc = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        enc = {key: value.to(device) for key, value in enc.items()}
        out = self.encoder(**enc)
        pooled = mean_pool(out.last_hidden_state, enc["attention_mask"])
        return self.head(pooled)


def _load_run_config(model_dir: Path) -> dict[str, Any]:
    run_config_path = model_dir / "run_config.json"
    if not run_config_path.is_file():
        return {}
    return json.loads(run_config_path.read_text())


def _load_multiintent_module_for_inference(
    checkpoint_path: Path,
    n_labels: int,
    device: torch.device,
    tokenizer_dir: Path,
) -> MultiIntentModule:
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"multiintent.pt missing at {checkpoint_path}")

    run_config = _load_run_config(tokenizer_dir)
    payload = torch.load(checkpoint_path, map_location=device)
    model_name = str(payload.get("model_name", run_config.get("model_name", DEFAULT_MODEL_NAME)))
    max_length = int(run_config.get("max_length", DEFAULT_MAX_LENGTH))
    expected_labels = payload.get("num_labels")
    if expected_labels is not None and int(expected_labels) != n_labels:
        raise ValueError(
            f"checkpoint num_labels={expected_labels} does not match label2id size={n_labels}"
        )

    module = MultiIntentModule(model_name, n_labels, max_length).to(device)
    module.encoder.load_state_dict(payload["encoder_state_dict"])
    module.head.load_state_dict(payload["head_state_dict"])
    if tokenizer_dir.is_dir():
        module.tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir))
    module.eval()
    return module


class MultiIntentClassifier:
    def __init__(
        self,
        model_dir: Path,
        module: Any = None,
        device: torch.device | None = None,
    ) -> None:
        model_dir = Path(model_dir)
        label2id_path = model_dir / "label2id.json"
        if not label2id_path.is_file():
            raise FileNotFoundError(f"label2id.json missing at {label2id_path}")

        label2id: dict[str, int] = json.loads(label2id_path.read_text())
        self._id2label = self._build_id2label(label2id)
        self._device = device or torch.device("cpu")

        if module is None:
            module = _load_multiintent_module_for_inference(
                checkpoint_path=model_dir / "multiintent.pt",
                n_labels=len(self._id2label),
                device=self._device,
                tokenizer_dir=model_dir,
            )
        self._module = module

        log.info(
            "MultiIntentClassifier ready: %d labels, device=%s, model_dir=%s",
            len(self._id2label),
            self._device,
            model_dir,
        )

    @staticmethod
    def _build_id2label(label2id: dict[str, int]) -> list[str]:
        n_labels = len(label2id)
        ids = {int(idx) for idx in label2id.values()}
        expected = set(range(n_labels))
        if ids != expected:
            raise ValueError(
                f"label ids must be contiguous 0..{n_labels - 1}; got {sorted(ids)}"
            )

        id2label = [""] * n_labels
        for label, idx in label2id.items():
            id2label[int(idx)] = str(label)
        return id2label

    def classify(self, command: str) -> Classification:
        with torch.inference_mode():
            logits = self._module.forward_texts([command], self._device)
            probs = torch.sigmoid(logits)
            idx = int(torch.argmax(probs, dim=1).item())
            confidence = float(probs[0, idx].item())
        return {
            "intent": self._id2label[idx],
            "confidence": confidence,
        }
