# MULTI-TASK ARCHITECTURE WITH CRF:
# 1. Sequence Classification (CLS token): Predict tool calls (GET_VITALS, CREATE_TASK, NAVIGATION_QUERY)
# 2. Token Classification + CRF: Extract task names (TEXT, TASK_NAME_START, TASK_NAME_CONT)
#    - CRF enforces valid transitions (e.g., START cannot follow START)

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from datasets import Dataset, DatasetDict
from transformers import (
    AutoModel,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    set_seed,
)

from decoding import normalize_task_predictions
from crf import CRF, create_transition_constraints, apply_transition_constraints


# Tool call labels (multi-label: a prompt can have multiple tools)
TOOL_LABELS = ["GET_VITALS", "CREATE_TASK", "NAVIGATION_QUERY"]
TOOL2ID = {tool: idx for idx, tool in enumerate(TOOL_LABELS)}


class MultiTaskModel(nn.Module):
    """BERT-based model with two heads:
    1. Sequence classification head (CLS token) for tool calls
    2. Token classification head + CRF for task name extraction
    """
    def __init__(self, base_model_name: str, num_token_labels: int, num_tool_labels: int, use_crf: bool = True):
        super().__init__()
        self.bert = AutoModel.from_pretrained(base_model_name)
        hidden_size = self.bert.config.hidden_size
        self.use_crf = use_crf

        # Head 1: Multi-label tool classification (from CLS token)
        self.tool_classifier = nn.Linear(hidden_size, num_tool_labels)

        # Head 2: Token classification for task names
        self.token_classifier = nn.Linear(hidden_size, num_token_labels)

        # CRF layer for enforcing valid token sequences
        if use_crf:
            self.crf = CRF(num_token_labels, batch_first=True)

        # Dropout
        self.dropout = nn.Dropout(0.2)

    def forward(self, input_ids, attention_mask, token_labels=None, tool_labels=None):
        # Get BERT outputs
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)

        # outputs.last_hidden_state: (batch, seq_len, hidden_size)
        sequence_output = outputs.last_hidden_state

        # CLS token (first token) for sequence classification
        cls_output = sequence_output[:, 0, :]  # (batch, hidden_size)

        # Tool classification logits (multi-label binary classification)
        tool_logits = self.tool_classifier(self.dropout(cls_output))  # (batch, 3)

        # Token classification emissions (before CRF)
        token_emissions = self.token_classifier(self.dropout(sequence_output))  # (batch, seq_len, num_token_labels)

        total_loss = None
        token_logits = token_emissions  # For compatibility

        if token_labels is not None and tool_labels is not None:
            # Loss 1: Multi-label BCE for tool classification
            tool_loss_fct = nn.BCEWithLogitsLoss()
            tool_loss = tool_loss_fct(tool_logits, tool_labels.float())

            # Loss 2: CRF negative log-likelihood for token classification
            if self.use_crf:
                # Create mask (1 for valid tokens, 0 for padding/special)
                crf_mask = (token_labels != -100).byte()
                # Replace -100 with 0 for CRF (it will be masked anyway)
                crf_labels = token_labels.clone()
                crf_labels[crf_labels == -100] = 0

                # CRF loss (negative log-likelihood)
                token_loss = self.crf(token_emissions, crf_labels, crf_mask)
            else:
                # Standard cross-entropy
                token_loss_fct = nn.CrossEntropyLoss()
                token_loss = token_loss_fct(token_emissions.view(-1, token_emissions.size(-1)), token_labels.view(-1))

            # Combined loss (weighted sum)
            total_loss = tool_loss + token_loss

        return {
            "loss": total_loss,
            "tool_logits": tool_logits,
            "token_logits": token_logits,
            "token_emissions": token_emissions,  # For CRF decoding
        }


def load_prompts(data_path: Path) -> List[Dict]:
    """Load the data.json format."""
    with data_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_label_lookup(prompts: List[Dict]) -> Dict[str, int]:
    """Build label2id mapping for token labels."""
    labels = set()
    for item in prompts:
        for part in item["parts"]:
            labels.add(part["type"])
    return {label: idx for idx, label in enumerate(sorted(labels))}


def convert_prompt_to_example(
    prompt: str,
    parts: List[Dict],
    tool_calls: List[str],
    tokenizer,
) -> Dict:
    """Convert a prompt with labeled parts and tool calls to training example."""
    # Build character-level label mapping for tokens
    char_labels = []
    reconstructed = ""
    for part in parts:
        text = part["text"]
        label = part["type"]
        reconstructed += text
        char_labels.extend([label] * len(text))

    if reconstructed != prompt:
        raise ValueError(f"Parts don't match prompt: {reconstructed!r} vs {prompt!r}")

    # Tokenize with offset mapping
    encoding = tokenizer(prompt, return_offsets_mapping=True)
    token_ids = encoding["input_ids"]
    offsets = encoding["offset_mapping"]

    tokens = []
    labels = []

    for token_id, (start, end) in zip(token_ids, offsets):
        if start == end:  # Special token (CLS, SEP, etc.)
            continue

        token = tokenizer.convert_ids_to_tokens([token_id])[0]
        label = char_labels[start]

        tokens.append(token)
        labels.append(label)

    # Tool labels (multi-hot encoding)
    tool_encoding = [1 if tool in tool_calls else 0 for tool in TOOL_LABELS]

    return {
        "tokens": tokens,
        "token_labels": labels,
        "tool_labels": tool_encoding,
    }


def load_and_convert_prompts(
    data_path: Path,
    tokenizer,
) -> Tuple[List[Dict], Dict[str, int]]:
    """Load data and convert to examples."""
    prompts = load_prompts(data_path)
    label2id = build_label_lookup(prompts)

    examples = []
    for item in prompts:
        example = convert_prompt_to_example(
            item["prompt"],
            item["parts"],
            item.get("tool_calls", []),
            tokenizer
        )
        examples.append(example)

    return examples, label2id


def encode_example(example: Dict, tokenizer, label2id: Dict[str, int]):
    tokens = example["tokens"]
    token_labels = example["token_labels"]
    tool_labels = example["tool_labels"]

    if len(tokens) != len(token_labels):
        raise ValueError("Token and label lengths do not match.")

    token_ids = tokenizer.convert_tokens_to_ids(tokens)
    input_ids = tokenizer.build_inputs_with_special_tokens(token_ids)
    special_ids = set(tokenizer.all_special_ids)
    special_mask = [1 if token_id in special_ids else 0 for token_id in input_ids]
    attention_mask = [1] * len(input_ids)

    encoded_token_labels: List[int] = []
    label_idx = 0
    for is_special in special_mask:
        if is_special:
            encoded_token_labels.append(-100)
        else:
            encoded_token_labels.append(label2id[token_labels[label_idx]])
            label_idx += 1

    if label_idx != len(token_labels):
        raise ValueError("Did not assign all labels to tokens.")

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_labels": encoded_token_labels,
        "tool_labels": tool_labels,
    }


def tokenize_dataset(dataset: DatasetDict, tokenizer, label2id: Dict[str, int]) -> DatasetDict:
    return dataset.map(
        lambda x: encode_example(x, tokenizer, label2id),
        remove_columns=["tokens", "token_labels"],
    )


def custom_collate_fn(batch, tokenizer):
    """Custom collate function to handle both token and tool labels."""
    # Extract fields - they're already lists from the dataset
    input_ids = [item["input_ids"] if isinstance(item["input_ids"], list) else item["input_ids"].tolist() for item in batch]
    attention_mask = [item["attention_mask"] if isinstance(item["attention_mask"], list) else item["attention_mask"].tolist() for item in batch]
    token_labels = [item["token_labels"] if isinstance(item["token_labels"], list) else item["token_labels"].tolist() for item in batch]
    tool_labels = [item["tool_labels"] if isinstance(item["tool_labels"], list) else item["tool_labels"].tolist() for item in batch]

    # Pad sequences
    max_len = max(len(ids) for ids in input_ids)

    padded_input_ids = []
    padded_attention_mask = []
    padded_token_labels = []

    for ids, mask, labels in zip(input_ids, attention_mask, token_labels):
        padding_length = max_len - len(ids)
        padded_input_ids.append(ids + [tokenizer.pad_token_id] * padding_length)
        padded_attention_mask.append(mask + [0] * padding_length)
        padded_token_labels.append(labels + [-100] * padding_length)

    return {
        "input_ids": torch.tensor(padded_input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(padded_attention_mask, dtype=torch.long),
        "token_labels": torch.tensor(padded_token_labels, dtype=torch.long),
        "tool_labels": torch.tensor(tool_labels, dtype=torch.long),
    }


def evaluate_model(model, dataloader: DataLoader, device: torch.device, label2id: Dict[str, int]) -> Dict:
    """Evaluate both tasks."""
    model.eval()

    # Token classification metrics
    token_correct = 0
    token_total = 0

    # Tool classification metrics
    tool_predictions = []
    tool_targets = []

    with torch.no_grad():
        for batch in dataloader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)

            # Token accuracy
            token_preds = outputs["token_logits"].argmax(dim=-1)
            mask = batch["token_labels"] != -100
            token_correct += ((token_preds == batch["token_labels"]) & mask).sum().item()
            token_total += mask.sum().item()

            # Tool predictions (multi-label)
            tool_preds = (torch.sigmoid(outputs["tool_logits"]) > 0.5).cpu()
            tool_predictions.extend(tool_preds.numpy())
            tool_targets.extend(batch["tool_labels"].cpu().numpy())

    token_accuracy = token_correct / token_total if token_total > 0 else 0.0

    # Calculate tool accuracy (exact match - all tools must be correct)
    tool_predictions = torch.tensor(tool_predictions)
    tool_targets = torch.tensor(tool_targets)
    tool_accuracy = (tool_predictions == tool_targets).all(dim=1).float().mean().item()

    return {
        "token_accuracy": token_accuracy,
        "tool_accuracy": tool_accuracy,
    }


def classify_prompt(
    prompt: str,
    model,
    tokenizer,
    id2label: Dict[int, str],
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Classify a prompt for both tool calls and task names.

    Returns:
        (tool_calls, token_predictions)
    """
    prompt = prompt.strip()
    if not prompt:
        return [], []

    encoding = tokenizer(prompt, return_tensors="pt", truncation=True)
    tokens = tokenizer.convert_ids_to_tokens(encoding["input_ids"][0])
    encoding = {key: value.to(model.bert.device) for key, value in encoding.items()}

    model.eval()
    with torch.no_grad():
        outputs = model(**encoding)

    # Tool predictions
    tool_probs = torch.sigmoid(outputs["tool_logits"][0])
    predicted_tools = [TOOL_LABELS[i] for i, prob in enumerate(tool_probs) if prob > 0.5]

    # Token predictions (use CRF Viterbi if available)
    if model.use_crf:
        # Create mask (all 1s since no padding in single example)
        mask = torch.ones(outputs["token_emissions"].shape[:2], dtype=torch.uint8, device=model.bert.device)
        # Viterbi decode
        best_paths = model.crf.decode(outputs["token_emissions"], mask)
        token_preds = best_paths[0]  # First (and only) batch item
    else:
        token_preds = outputs["token_logits"].argmax(dim=-1)[0].tolist()

    special_tokens = set(tokenizer.all_special_tokens)
    token_results: List[Tuple[str, str]] = []
    for token, pred_id in zip(tokens, token_preds):
        if token in special_tokens:
            continue
        token_results.append((token, id2label[int(pred_id)]))

    # With CRF, normalization might not be needed, but keep for safety
    normalized_tokens = normalize_task_predictions(token_results)

    return predicted_tools, normalized_tokens


def main():
    set_seed(42)

    # Load tokenizer
    model_name = "distilbert-base-uncased"
    cache_dir = Path("./model_cache")
    cache_dir.mkdir(exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)

    # Load and convert data
    data_path = Path("data.json")
    examples, label2id = load_and_convert_prompts(data_path, tokenizer)
    id2label = {idx: label for label, idx in label2id.items()}

    print(f"Token labels: {label2id}")
    print(f"Tool labels: {TOOL2ID}")

    raw_dataset = Dataset.from_list(examples)
    if len(raw_dataset) > 1:
        dataset_dict = raw_dataset.train_test_split(test_size=0.2, seed=42, shuffle=True)
    else:
        dataset_dict = DatasetDict(train=raw_dataset, test=raw_dataset)

    tokenized = tokenize_dataset(dataset_dict, tokenizer, label2id)

    tokenized["train"].set_format(type="torch")
    tokenized["test"].set_format(type="torch")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Initialize multi-task model with CRF
    model = MultiTaskModel(
        base_model_name=model_name,
        num_token_labels=len(label2id),
        num_tool_labels=len(TOOL_LABELS),
        use_crf=True,
    )
    model.to(device)

    # Apply transition constraints to CRF
    if model.use_crf:
        constraints = create_transition_constraints(label2id)
        apply_transition_constraints(model.crf, constraints)
        print(f"Applied CRF transition constraints")
        print(f"Forbidden transitions: START->START, CONT->START")

    train_loader = DataLoader(
        tokenized["train"],
        batch_size=16,
        shuffle=True,
        collate_fn=lambda batch: custom_collate_fn(batch, tokenizer)
    )
    val_loader = DataLoader(
        tokenized["test"],
        batch_size=16,
        shuffle=False,
        collate_fn=lambda batch: custom_collate_fn(batch, tokenizer)
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)

    num_epochs = 3
    global_step = 0
    patience = 20
    best_val_acc = 0.0
    steps_without_improvement = 0
    best_state_dict = None
    should_stop = False

    print("\nStarting training...")
    for epoch in range(num_epochs):
        for batch in train_loader:
            model.train()
            batch = {key: value.to(device) for key, value in batch.items()}

            outputs = model(**batch)
            loss = outputs["loss"]
            loss.backward()

            optimizer.step()
            optimizer.zero_grad()

            # Evaluate
            metrics = evaluate_model(model, val_loader, device, label2id)
            global_step += 1

            print(
                f"epoch={epoch + 1} step={global_step} "
                f"loss={loss.item():.4f} "
                f"token_acc={metrics['token_accuracy']:.4f} "
                f"tool_acc={metrics['tool_accuracy']:.4f}"
            )

            # Track best model based on combined accuracy
            combined_acc = (metrics['token_accuracy'] + metrics['tool_accuracy']) / 2
            if combined_acc > best_val_acc + 1e-4:
                best_val_acc = combined_acc
                steps_without_improvement = 0
                best_state_dict = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            else:
                steps_without_improvement += 1
                if steps_without_improvement >= patience:
                    should_stop = True
                    break
        if should_stop:
            break

    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    # Test example
    example_prompt = "yo check hows my heart doing then add a task to go to the rocket"
    tools, token_preds = classify_prompt(example_prompt, model, tokenizer, id2label)

    print("\n" + "="*70)
    print("Example prompt classification:")
    print(example_prompt)
    print(f"\nPredicted tools: {tools}")
    print("\nToken predictions:")
    for word, label in token_preds:
        print(f"  {word:<20} -> {label}")

    # Save model
    output_dir = Path("outputs/final-model")
    output_dir.mkdir(parents=True, exist_ok=True)

    torch.save({
        'model_state_dict': model.state_dict(),
        'label2id': label2id,
        'id2label': id2label,
        'tool2id': TOOL2ID,
        'tool_labels': TOOL_LABELS,
        'use_crf': model.use_crf,
    }, output_dir / "model.pt")

    tokenizer.save_pretrained(output_dir)

    print(f"\nModel saved to {output_dir}")


if __name__ == "__main__":
    main()
