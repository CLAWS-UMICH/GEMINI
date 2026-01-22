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
from sklearn.metrics import f1_score

from simpledatacombine import get_data_and_labels


# === CONFIGURATION ===
USE_GPU = True  # Set to False to force CPU training

# Labels - will be populated dynamically from the data
TOOL_LABELS = []
TOKEN_LABELS = [] 

THRESHOLD_LOSS_WEIGHT = 0.5 # Deprecated, kept for variable cleaning if needed
TAG_LOSS_WEIGHT = 10.0  # Prioritize tool classification over token labeling



def compute_count_loss(count_pred, count_labels):
    """MSE loss for the number of tools."""
    return nn.functional.mse_loss(count_pred.squeeze(-1), count_labels.float())

class TwoHeadModel(nn.Module):
    """Embedding model with two linear heads."""

    def __init__(self, base_model: str, num_tools: int, num_token_labels: int, token_weights=None):
        super().__init__()
        # Enable output_hidden_states to access all layers
        self.encoder = AutoModel.from_pretrained(base_model, output_hidden_states=True)
        hidden = self.encoder.config.hidden_size
        self.num_tools = num_tools

        # Learnable weights for each layer (num_hidden_layers + 1 for embedding layer)
        # Initialize to favor the last layer slightly or keep uniform, but letting it learn is key.
        n_layers = self.encoder.config.num_hidden_layers + 1
        self.layer_weights = nn.Parameter(torch.ones(n_layers))

        # Head 1: Overall tags from weighted [CLS] token
        self.tag_head = nn.Linear(hidden, num_tools)
        
        # Head 3: Predicting the number of tools (regression)
        self.count_head = nn.Linear(hidden, 1)

        # Head 2: Token-level classification usually benefits most from the last layer
        # giving it access to all layers might be overkill or good, but user asked for 
        # "head that predicts the tags and the # of labels" to have this access.
        # We'll keep token head on the last hidden state for now to keep it simple as requested.
        self.token_head = nn.Sequential(
            nn.Linear(hidden, hidden * 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden * 2, hidden),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, num_token_labels)
        )

        # Class weights for imbalanced token labels
        if token_weights is not None:
            self.register_buffer("token_weights", token_weights)
        else:
            self.token_weights = None

    def forward(self, input_ids, attention_mask, tag_labels=None, token_labels=None, count_labels=None):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        
        # Stack all hidden states: (n_layers, batch, seq, hidden)
        all_hidden_states = torch.stack(out.hidden_states)
        
        # We only want the [CLS] token from each layer: (n_layers, batch, hidden)
        all_cls_tokens = all_hidden_states[:, :, 0, :]
        
        # Compute normalized weights: (n_layers,)
        norm_weights = nn.functional.softmax(self.layer_weights, dim=0)
        
        # Weighted sum: (batch, hidden)
        # Broadcast weights across batch and hidden dims
        weighted_cls = torch.sum(all_cls_tokens * norm_weights.view(-1, 1, 1), dim=0)

        tool_logits = self.tag_head(weighted_cls)  # (batch, num_tools)
        count_pred = self.count_head(weighted_cls) # (batch, 1)

        # All tokens for token-level (using last hidden state)
        last_hidden_state = out.last_hidden_state
        token_logits = self.token_head(last_hidden_state)  # (batch, seq, num_token_labels)

        loss = None
        if tag_labels is not None and token_labels is not None and count_labels is not None:
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

            count_loss_val = compute_count_loss(count_pred, count_labels)
            loss = (TAG_LOSS_WEIGHT * tag_loss) + token_loss + count_loss_val

        return {
            "loss": loss,
            "tag_logits": tool_logits,
            "count_pred": count_pred,
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
        prompt = item["prompt"].lower()
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
        
        # Count label (unique tools)
        unique_tools = set(tools)
        count_label = len(unique_tools)

        return {
            "input_ids": torch.tensor(input_ids),
            "attention_mask": torch.tensor(attention_mask),
            "token_labels": torch.tensor(token_labels),
            "tag_labels": torch.tensor(tag_labels),
            "count_labels": torch.tensor(count_label, dtype=torch.float32),
        }


def collate(batch):
    """Pad batch to same length."""
    max_len = max(b["input_ids"].size(0) for b in batch)

    input_ids = []
    attention_mask = []
    token_labels = []
    tag_labels = []
    count_labels = []

    for b in batch:
        pad_len = max_len - b["input_ids"].size(0)
        input_ids.append(nn.functional.pad(b["input_ids"], (0, pad_len), value=0))
        attention_mask.append(nn.functional.pad(b["attention_mask"], (0, pad_len), value=0))
        token_labels.append(nn.functional.pad(b["token_labels"], (0, pad_len), value=-100))
        tag_labels.append(b["tag_labels"])
        count_labels.append(b["count_labels"])

    return {
        "input_ids": torch.stack(input_ids),
        "attention_mask": torch.stack(attention_mask),
        "token_labels": torch.stack(token_labels),
        "tag_labels": torch.stack(tag_labels),
        "count_labels": torch.stack(count_labels),
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


def log_failures(model, val_loader, tokenizer, device, out_path, tool_labels, token_labels):
    """
    Runs a pass on validation set and logs incorrect predictions to a file.
    """
    model.eval()
    all_failures = []
    
    # Inverse mappings for readability
    idx_to_tool = {i: t for i, t in enumerate(tool_labels)}
    idx_to_token = {i: t for i, t in enumerate(token_labels)}

    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            tag_labels = batch["tag_labels"].to(device)
            token_labels_gt = batch["token_labels"].to(device) # Ground Truth
            
            # Forward pass
            outputs = model(input_ids, attention_mask)
            tag_logits = outputs["tag_logits"]
            token_logits = outputs["token_logits"]

            # Predictions
            # Tags: sigmoid > 0.5
            pred_tags = (torch.sigmoid(tag_logits) > 0.5).int()
            
            # Tokens: argmax
            pred_tokens = torch.argmax(token_logits, dim=-1)

            # Iterate over batch
            batch_size = input_ids.size(0)
            for i in range(batch_size):
                # Check for mismatch
                tags_match = torch.equal(pred_tags[i], tag_labels[i].int())
                
                # For tokens, ignore padding (-100) in ground truth
                mask = token_labels_gt[i] != -100
                tokens_match = torch.equal(pred_tokens[i][mask], token_labels_gt[i][mask])

                if not tags_match or not tokens_match:
                    # Decode inputs
                    prompt = tokenizer.decode(input_ids[i], skip_special_tokens=True)
                    
                    # Get readable lists for tags
                    expected_tags_list = [idx_to_tool[j] for j, val in enumerate(tag_labels[i]) if val == 1]
                    predicted_tags_list = [idx_to_tool[j] for j, val in enumerate(pred_tags[i]) if val == 1]
                    
                    # Get readable lists for tokens (masked)
                    gt_tok_indices = token_labels_gt[i][mask].cpu().tolist()
                    pred_tok_indices = pred_tokens[i][mask].cpu().tolist()
                    
                    expected_tokens_list = [idx_to_token.get(idx, "UNK") for idx in gt_tok_indices]
                    predicted_tokens_list = [idx_to_token.get(idx, "UNK") for idx in pred_tok_indices]

                    all_failures.append(
                        f"PROMPT: {prompt}\n"
                        f"EXPECTED TAGS: {expected_tags_list}\n"
                        f"PREDICTED TAGS: {predicted_tags_list}\n"
                        f"EXPECTED TOKENS: {expected_tokens_list}\n"
                        f"PREDICTED TOKENS: {predicted_tokens_list}\n"
                        f"{'-'*40}\n"
                    )

    if all_failures:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.writelines(all_failures)
        print(f"Logged {len(all_failures)} incorrect predictions to {out_path}")
    else:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("No incorrect predictions found on validation set!\n")
        print("Perfect validation score! No errors logged.")

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

    # Simple AdamW optimizer - proven for fine-tuning pretrained transformers
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)

    # Training settings
    num_epochs = 80
    warmup_epochs = 3
    base_lr = 2e-5
    
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
    patience = 10
    patience_counter = 0
    
    # Gradient clipping value
    max_grad_norm = 1.0

    for epoch in range(num_epochs):
        # Adjust learning rate based on schedule
        lr_mult = get_lr_multiplier(epoch)
        for param_group in optimizer.param_groups:
            param_group['lr'] = base_lr * lr_mult
        
        # Train
        model.train()
        total_loss = 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(**batch)
            loss = out["loss"]

            optimizer.zero_grad()
            loss.backward()
            
            # Gradient clipping for stability
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            
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

        # Storage for F1 calculation
        all_pred_tags = []
        all_true_tags = []
        all_pred_tokens = []
        all_true_tokens = []

        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                out = model(**batch)

                # Accumulate val loss
                val_loss += out["loss"].item()

                # Tag accuracy (exact match)
                # Tag accuracy (top k based on count)
                tag_probs = torch.sigmoid(out["tag_logits"])
                count_preds = out["count_pred"].squeeze(1)
                
                # Inference logic: k = round(count_pred)
                k_list = torch.round(count_preds).int()
                k_list = torch.clamp(k_list, min=0)
                
                # Check for exact match of set of tools
                for i in range(len(batch["tag_labels"])):
                    # Get predicted indices
                    k = k_list[i].item()

                    # F1 storage
                    pred_vec = (tag_probs[i] > 0.5).int().cpu().numpy()
                    true_vec = batch["tag_labels"][i].cpu().numpy()
                    all_pred_tags.append(pred_vec)
                    all_true_tags.append(true_vec)

                    if k > 0:
                        _, top_indices = torch.topk(tag_probs[i], k)
                        pred_indices = set(top_indices.tolist())
                    else:
                        pred_indices = set()
                    
                    # Get true indices
                    true_indices = set((batch["tag_labels"][i] == 1).nonzero(as_tuple=True)[0].tolist())
                    
                    if pred_indices == true_indices:
                        tag_correct += 1
                        
                tag_total += batch["tag_labels"].size(0)

                # Token accuracy
                token_preds = out["token_logits"].argmax(dim=-1)
                mask = batch["token_labels"] != -100
                token_correct += ((token_preds == batch["token_labels"]) & mask).sum().item()
                token_total += mask.sum().item()

                # Collect for F1
                valid_preds = token_preds[mask].cpu().numpy()
                valid_true = batch["token_labels"][mask].cpu().numpy()
                all_pred_tokens.extend(valid_preds)
                all_true_tokens.extend(valid_true)

        avg_val_loss = val_loss / len(val_loader)
        tag_acc = tag_correct / tag_total if tag_total > 0 else 0
        token_acc = token_correct / token_total if token_total > 0 else 0
        
        # Calculate F1
        tag_f1 = f1_score(all_true_tags, all_pred_tags, average='macro')
        token_f1 = f1_score(all_true_tokens, all_pred_tokens, average='macro')

        combined = (tag_acc + token_acc) / 2

        print(f"Epoch {epoch+1}: train_loss={avg_loss:.4f} val_loss={avg_val_loss:.4f} tag_acc={tag_acc:.4f} token_acc={token_acc:.4f}")
        print(f"Metrics: Tag F1={tag_f1:.4f} | Token F1={token_f1:.4f}")

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

    print(f"\nSaved PyTorch model to {out_dir}")

    # Log failures and incorrect predictions
    print("Generating failure log...")
    log_failures(model, val_loader, tokenizer, device, "incorrect_predictions.txt", TOOL_LABELS, TOKEN_LABELS)

    # Save labels metadata as JSON for inference
    with open(out_dir / "labels.json", "w") as f:
        json.dump({
            "tool_labels": TOOL_LABELS,
            "token_labels": TOKEN_LABELS,
        }, f, indent=2)

    print(f"Saved labels to {out_dir / 'labels.json'}")

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
        count_pred = out["count_pred"][0].item()
        
        k = int(round(count_pred))
        k = max(0, k)
        
        if k > 0:
             _, top_indices = torch.topk(tag_probs, k)
             pred_tags = [TOOL_LABELS[i] for i in top_indices.tolist()]
        else:
             pred_tags = []

        # Tokens
        token_preds = out["token_logits"].argmax(dim=-1)[0]

        print(f"\nPrompt: {prompt}")
        print(f"Tags: {pred_tags}")
        print(f"Count Pred: {count_pred:.2f} (k={k})")
        print("Tokens:")
        for tok, pred in zip(tokens, token_preds):
            if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
                print(f"  {tok:20} -> {id2token[pred.item()]}")


if __name__ == "__main__":
    train()
