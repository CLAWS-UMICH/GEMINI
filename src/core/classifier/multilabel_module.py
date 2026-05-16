"""Vendored multilabel encoder+head module.

Verbatim from the teammate's
`intent_model/src/intent_model/train_intent_model.py` (mean_pool @ L318,
MultilabelIntentModule @ L483, load_multilabel_module_for_inference @ L505).

We don't pip-install their package because it pins torch==2.2.2 and we're
on torch≥2.9. The API surface used here (AutoTokenizer/AutoModel.from_pretrained,
nn.Linear, torch.load) is stable across both pins.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer


def mean_pool(last_hidden: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    summed = torch.sum(last_hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-09)
    return summed / counts


class MultilabelIntentModule(nn.Module):
    def __init__(self, model_name: str, n_labels: int) -> None:
        super().__init__()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.encoder = AutoModel.from_pretrained(model_name)
        hid = int(self.encoder.config.hidden_size)
        self.head = nn.Linear(hid, n_labels)

    def forward_texts(self, texts: list[str], device: torch.device) -> torch.Tensor:
        enc = self.tokenizer(
            texts, padding=True, truncation=True, max_length=256, return_tensors="pt"
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        out = self.encoder(**enc)
        pooled = mean_pool(out.last_hidden_state, enc["attention_mask"])
        return self.head(pooled)


def load_multilabel_module_for_inference(
    checkpoint_path: Path,
    n_labels: int,
    device: torch.device,
    tokenizer_dir: Path | None = None,
) -> MultilabelIntentModule:
    payload = torch.load(checkpoint_path, map_location=device)
    model_name = str(payload.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"))
    module = MultilabelIntentModule(model_name, n_labels).to(device)
    module.encoder.load_state_dict(payload["encoder_state_dict"])
    module.head.load_state_dict(payload["head_state_dict"])
    if tokenizer_dir is not None and Path(tokenizer_dir).is_dir():
        module.tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir))
    module.eval()
    return module
