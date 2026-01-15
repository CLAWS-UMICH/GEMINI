"""
Simple two-head embedding model fine-tuning.

Head 1: Linear layer for overall task tags plus a learned threshold
Head 2: Linear layer for token-level prediction (TEXT, TASK_NAME, WAYPOINT_NAME, etc.)
"""

import json
import math
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

from simpledatacombine import get_data_and_labels


# === CONFIGURATION ===
USE_GPU = True  # Set to False to force CPU training

# Labels - will be populated dynamically from the data
TOOL_LABELS = []
TOKEN_LABELS = [] 

THRESHOLD_LOSS_WEIGHT = 0.5
TAG_LOSS_WEIGHT = 10.0  # Prioritize tool classification over token labeling


def compute_threshold_loss(tool_logits, threshold_logit, tag_labels):
    """Encourage threshold to sit between positive and negative tool probs."""
    tool_probs = torch.sigmoid(tool_logits)
    threshold = torch.sigmoid(threshold_logit).unsqueeze(1)

    pos_mask = tag_labels > 0.5
    neg_mask = ~pos_mask

    loss = tool_logits.new_tensor(0.0)
    if pos_mask.any().item():
        loss = loss + nn.functional.softplus(threshold - tool_probs)[pos_mask].mean()
    if neg_mask.any().item():
        loss = loss + nn.functional.softplus(tool_probs - threshold)[neg_mask].mean()

    return loss

class TwoHeadModel(nn.Module):
    """Embedding model with two linear heads."""

    def __init__(self, base_model: str, num_tools: int, num_token_labels: int, token_weights=None):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = self.encoder.config.hidden_size
        self.num_tools = num_tools

        # Head 1: Overall tags from [CLS] token
        self.tag_head = nn.Linear(hidden, num_tools + 1)

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
        tag_logits = self.tag_head(cls)  # (batch, num_tools + 1)
        tool_logits = tag_logits[:, : self.num_tools]
        threshold_logit = tag_logits[:, self.num_tools]

        # All tokens for token-level
        token_logits = self.token_head(hidden_states)  # (batch, seq, num_token_labels)

        loss = None
        if tag_labels is not None and token_labels is not None:
            # Multi-label BCE for tags
            tag_loss = nn.functional.binary_cross_entropy_with_logits(
                tool_logits, tag_labels.float()
            )

            # Cross entropy for tokens with class weights (ignoring -100)
            token_loss = nn.functional.cross_entropy(
                token_logits.view(-1, token_logits.size(-1)),
                token_labels.view(-1),
                weight=self.token_weights,
                ignore_index=-100,
            )

            threshold_loss = compute_threshold_loss(tool_logits, threshold_logit, tag_labels)
            loss = (TAG_LOSS_WEIGHT * tag_loss) + token_loss + (THRESHOLD_LOSS_WEIGHT * threshold_loss)

        return {
            "loss": loss,
            "tag_logits": tool_logits,
            "threshold_logit": threshold_logit,
            "token_logits": token_logits,
        }


class PromptDataset(Dataset):
    """Dataset from combined singletools data."""

    def __init__(self, data: list, tokenizer, tool_labels: list, token_labels: list):
        self.data = data
        self.tokenizer = tokenizer
        self.tool_labels = tool_labels
        self.token_labels = token_labels

        self.tool2id = {t: i for i, t in enumerate(tool_labels)}
        self.label2id = {l: i for i, l in enumerate(token_labels)}

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

        # Validate: parts must cover the entire prompt
        parts_text = "".join(p["text"] for p in parts)
        if len(char_labels) != len(prompt):
            raise ValueError(
                f"Data mismatch at index {idx}!\n"
                f"  Prompt ({len(prompt)} chars): {prompt!r}\n"
                f"  Parts ({len(parts_text)} chars): {parts_text!r}\n"
                f"  Tools: {tools}"
            )

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
        tag_labels = [1 if t in tools else 0 for t in self.tool_labels]

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
    global TOOL_LABELS, TOKEN_LABELS
    
    if USE_GPU and torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print(f"Using device: {device}")

    model_name = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Load data from singletools directory
    data, TOOL_LABELS, TOKEN_LABELS = get_data_and_labels()
    
    dataset = PromptDataset(data, tokenizer, TOOL_LABELS, TOKEN_LABELS)
    print(f"Loaded {len(dataset)} examples")

    # Compute class weights for imbalanced token labels
    token_weights = compute_class_weights(dataset)
    print(f"Token class weights: {dict(zip(TOKEN_LABELS, token_weights.tolist()))}")

    # Split train/val
    train_size = int(0.9 * len(dataset))
    val_size = len(dataset) - train_size
    train_set, val_set = torch.utils.data.random_split(dataset, [train_size, val_size])

    # Larger batch size for better gradient estimates
    train_loader = DataLoader(train_set, batch_size=32, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_set, batch_size=32, shuffle=False, collate_fn=collate)

    model = TwoHeadModel(model_name, len(TOOL_LABELS), len(TOKEN_LABELS), token_weights.to(device))
    model.to(device)

    # Use Muon optimizer - PyTorch's built-in implementation
    # Muon uses orthogonalized momentum (Newton-Schulz) which can help with faster convergence
    # Note: Muon is for 2D params (weight matrices), use AdamW for embeddings/bias/layernorm
    
    # Separate parameters: use Muon for 2D weight matrices, AdamW for others
    embed_params = []
    muon_params = []
    for name, param in model.named_parameters():
        if 'embedding' in name.lower() or 'LayerNorm' in name or 'bias' in name or param.ndim != 2:
            embed_params.append(param)
        else:
            muon_params.append(param)
    
    optimizer = torch.optim.Muon(
        muon_params,
        lr=0.02,  # Muon uses higher learning rates
        momentum=0.95,
        nesterov=True,
        weight_decay=0.01,
        ns_steps=5,
        adjust_lr_fn='match_rms_adamw',  # Match AdamW RMS for easier LR tuning
    )
    
    # Separate AdamW for embeddings/bias/layernorm (non-2D params)
    optimizer_embed = torch.optim.AdamW(embed_params, lr=3e-4, weight_decay=0.01)

    # Learning rate schedulers with warmup
    num_epochs = 100
    warmup_epochs = 5
    
    def get_lr_multiplier(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        else:
            # Cosine decay
            progress = (epoch - warmup_epochs) / (num_epochs - warmup_epochs)
            return 0.5 * (1 + math.cos(math.pi * progress))
    
    best_acc = 0
    best_state = None
    best_val_loss = float("inf")
    patience = 15  # Increased patience since we're using warmup
    patience_counter = 0
    
    # Gradient clipping value
    max_grad_norm = 1.0

    for epoch in range(num_epochs):
        # Adjust learning rate based on schedule
        lr_mult = get_lr_multiplier(epoch)
        for param_group in optimizer.param_groups:
            param_group['lr'] = 0.02 * lr_mult
        for param_group in optimizer_embed.param_groups:
            param_group['lr'] = 3e-4 * lr_mult
        
        # Train
        model.train()
        total_loss = 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = out["loss"]

            optimizer.zero_grad()
            optimizer_embed.zero_grad()
            loss.backward()
            
            # Gradient clipping for stability
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            
            optimizer.step()
            optimizer_embed.step()

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
                tag_probs = torch.sigmoid(out["tag_logits"])
                thresholds = torch.sigmoid(out["threshold_logit"]).unsqueeze(1)
                tag_preds = (tag_probs > thresholds).int()
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

        # Early stopping check based on validation loss
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping triggered! Val loss hasn't improved for {patience} epochs.")
                break

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
        threshold = torch.sigmoid(out["threshold_logit"][0]).item()
        pred_tags = [TOOL_LABELS[i] for i, p in enumerate(tag_probs) if p > threshold]

        # Tokens
        token_preds = out["token_logits"].argmax(dim=-1)[0]

        print(f"\nPrompt: {prompt}")
        print(f"Tags: {pred_tags}")
        print(f"Threshold: {threshold:.2f}")
        print("Tokens:")
        for tok, pred in zip(tokens, token_preds):
            if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
                print(f"  {tok:20} -> {id2token[pred.item()]}")


if __name__ == "__main__":
    train()
