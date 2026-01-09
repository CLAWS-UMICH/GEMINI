"""
Simple two-head embedding model fine-tuning.

Head 1: Linear layer for overall task tags (GET_VITALS, CREATE_TASK, NAVIGATION_QUERY)
Head 2: Linear layer for token-level prediction (TEXT, TASK_NAME_START, TASK_NAME_CONT)
"""

import json
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer


# Labels
TOOL_LABELS = ["GET_VITALS", "CREATE_TASK", "NAVIGATION_QUERY"]
TOKEN_LABELS = ["TASK_NAME_CONT", "TASK_NAME_START", "TEXT"] 


class TwoHeadModel(nn.Module):
    """Embedding model with two linear heads."""

    def __init__(self, base_model: str, num_tools: int, num_token_labels: int, token_weights=None):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = self.encoder.config.hidden_size

        # Head 1: Overall tags from [CLS] token
        self.tag_head = nn.Linear(hidden, num_tools)

        # Head 2: Token-level classification
        self.token_head = nn.Linear(hidden, num_token_labels)

        # Class weights for imbalanced token labels
        if token_weights is not None:
            self.register_buffer("token_weights", token_weights)
        else:
            self.token_weights = None

    def forward(self, input_ids, attention_mask, tag_labels=None, token_labels=None):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        hidden_states = out.last_hidden_state  # (batch, seq, hidden)

        # CLS token for overall tags
        cls = hidden_states[:, 0, :]
        tag_logits = self.tag_head(cls)  # (batch, num_tools)

        # All tokens for token-level
        token_logits = self.token_head(hidden_states)  # (batch, seq, num_token_labels)

        loss = None
        if tag_labels is not None and token_labels is not None:
            # Multi-label BCE for tags
            tag_loss = nn.functional.binary_cross_entropy_with_logits(
                tag_logits, tag_labels.float()
            )

            # Cross entropy for tokens with class weights (ignoring -100)
            token_loss = nn.functional.cross_entropy(
                token_logits.view(-1, token_logits.size(-1)),
                token_labels.view(-1),
                weight=self.token_weights,
                ignore_index=-100,
            )

            loss = tag_loss + token_loss

        return {"loss": loss, "tag_logits": tag_logits, "token_logits": token_logits}


class PromptDataset(Dataset):
    """Dataset from data.json."""

    def __init__(self, data_path: str, tokenizer):
        with open(data_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.tokenizer = tokenizer

        self.tool2id = {t: i for i, t in enumerate(TOOL_LABELS)}
        self.label2id = {l: i for i, l in enumerate(TOKEN_LABELS)}

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        prompt = item["prompt"]
        parts = item["parts"]
        tools = item.get("tool_calls", [])

        # Character-level labels
        char_labels = []
        for part in parts:
            char_labels.extend([part["type"]] * len(part["text"]))

        # Tokenize
        enc = self.tokenizer(prompt, return_offsets_mapping=True, truncation=True, max_length=128)
        input_ids = enc["input_ids"]
        attention_mask = enc["attention_mask"]
        offsets = enc["offset_mapping"]

        # Map tokens to labels
        token_labels = []
        for start, end in offsets:
            if start == end:  # special token
                token_labels.append(-100)
            else:
                label = char_labels[start]
                token_labels.append(self.label2id[label])

        # Tool labels (multi-hot)
        tag_labels = [1 if t in tools else 0 for t in TOOL_LABELS]

        return {
            "input_ids": torch.tensor(input_ids),
            "attention_mask": torch.tensor(attention_mask),
            "token_labels": torch.tensor(token_labels),
            "tag_labels": torch.tensor(tag_labels),
        }


def collate(batch):
    """Pad batch to same length."""
    max_len = max(b["input_ids"].size(0) for b in batch)

    input_ids = []
    attention_mask = []
    token_labels = []
    tag_labels = []

    for b in batch:
        pad_len = max_len - b["input_ids"].size(0)
        input_ids.append(nn.functional.pad(b["input_ids"], (0, pad_len), value=0))
        attention_mask.append(nn.functional.pad(b["attention_mask"], (0, pad_len), value=0))
        token_labels.append(nn.functional.pad(b["token_labels"], (0, pad_len), value=-100))
        tag_labels.append(b["tag_labels"])

    return {
        "input_ids": torch.stack(input_ids),
        "attention_mask": torch.stack(attention_mask),
        "token_labels": torch.stack(token_labels),
        "tag_labels": torch.stack(tag_labels),
    }


def compute_class_weights(dataset):
    """Compute inverse frequency weights for token labels."""
    from collections import Counter
    counts = Counter()
    for i in range(len(dataset)):
        item = dataset[i]
        labels = item["token_labels"]
        for label in labels.tolist():
            if label != -100:
                counts[label] += 1

    total = sum(counts.values())
    num_classes = len(TOKEN_LABELS)

    # Inverse frequency: weight = total / (num_classes * count)
    weights = []
    for i in range(num_classes):
        count = counts.get(i, 1)
        weights.append(total / (num_classes * count))

    return torch.tensor(weights, dtype=torch.float32)


def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    model_name = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    dataset = PromptDataset("data.json", tokenizer)
    print(f"Loaded {len(dataset)} examples")

    # Compute class weights for imbalanced token labels
    token_weights = compute_class_weights(dataset)
    print(f"Token class weights: {dict(zip(TOKEN_LABELS, token_weights.tolist()))}")

    # Split train/val
    train_size = int(0.9 * len(dataset))
    val_size = len(dataset) - train_size
    train_set, val_set = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_set, batch_size=16, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_set, batch_size=16, shuffle=False, collate_fn=collate)

    model = TwoHeadModel(model_name, len(TOOL_LABELS), len(TOKEN_LABELS), token_weights.to(device))
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)

    best_acc = 0
    best_state = None

    for epoch in range(10):
        # Train
        model.train()
        total_loss = 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = out["loss"]

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)

        # Eval
        model.eval()
        tag_correct = 0
        tag_total = 0
        token_correct = 0
        token_total = 0
        val_loss = 0

        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                out = model(**batch)

                # Accumulate val loss
                val_loss += out["loss"].item()

                # Tag accuracy (exact match)
                tag_preds = (torch.sigmoid(out["tag_logits"]) > 0.5).int()
                tag_correct += (tag_preds == batch["tag_labels"]).all(dim=1).sum().item()
                tag_total += batch["tag_labels"].size(0)

                # Token accuracy
                token_preds = out["token_logits"].argmax(dim=-1)
                mask = batch["token_labels"] != -100
                token_correct += ((token_preds == batch["token_labels"]) & mask).sum().item()
                token_total += mask.sum().item()

        avg_val_loss = val_loss / len(val_loader)
        tag_acc = tag_correct / tag_total if tag_total > 0 else 0
        token_acc = token_correct / token_total if token_total > 0 else 0
        combined = (tag_acc + token_acc) / 2

        print(f"Epoch {epoch+1}: train_loss={avg_loss:.4f} val_loss={avg_val_loss:.4f} tag_acc={tag_acc:.4f} token_acc={token_acc:.4f}")

        if combined > best_acc:
            best_acc = combined
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # Restore best and save
    if best_state:
        model.load_state_dict(best_state)

    out_dir = Path("outputs/simple-model")
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.save({
        "model_state_dict": model.state_dict(),
        "tool_labels": TOOL_LABELS,
        "token_labels": TOKEN_LABELS,
    }, out_dir / "model.pt")
    tokenizer.save_pretrained(out_dir)

    print(f"\nSaved to {out_dir}")

    # Demo
    demo(model, tokenizer, device)


def demo(model, tokenizer, device):
    """Run a quick demo prediction."""
    model.eval()

    prompts = [
        "show me my vitals",
        "create a task called fix the engine",
        "add a task for checking inventory then show vitals",
    ]

    id2token = {i: l for i, l in enumerate(TOKEN_LABELS)}

    print("\n" + "=" * 60)
    print("Demo predictions:")

    for prompt in prompts:
        enc = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
        enc = {k: v.to(device) for k, v in enc.items()}
        tokens = tokenizer.convert_ids_to_tokens(enc["input_ids"][0])

        with torch.no_grad():
            out = model(**enc)

        # Tags
        tag_probs = torch.sigmoid(out["tag_logits"][0])
        pred_tags = [TOOL_LABELS[i] for i, p in enumerate(tag_probs) if p > 0.5]

        # Tokens
        token_preds = out["token_logits"].argmax(dim=-1)[0]

        print(f"\nPrompt: {prompt}")
        print(f"Tags: {pred_tags}")
        print("Tokens:")
        for tok, pred in zip(tokens, token_preds):
            if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
                print(f"  {tok:20} -> {id2token[pred.item()]}")


if __name__ == "__main__":
    train()

