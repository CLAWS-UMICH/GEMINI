# NAVIGATION_QUERY
# CREATE_TASK
#  - extract task names
# GET_VITALS

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import torch
from torch.utils.data import DataLoader

from datasets import Dataset, DatasetDict
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    set_seed,
)

from decoding import normalize_task_predictions


def load_prompts(data_path: Path) -> List[Dict]:
    """Load the prompts.json format."""
    with data_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_label_lookup(prompts: List[Dict]) -> Dict[str, int]:
    """Build label2id mapping from prompts data."""
    labels = set()
    for item in prompts:
        for part in item["parts"]:
            labels.add(part["type"])
    return {label: idx for idx, label in enumerate(sorted(labels))}


def convert_prompt_to_example(
    prompt: str,
    parts: List[Dict],
    tokenizer,
) -> Dict[str, List[str]]:
    """Convert a prompt with labeled parts to token-level labels."""
    # Build character-level label mapping
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

    return {"tokens": tokens, "labels": labels}


def load_and_convert_prompts(
    data_path: Path,
    tokenizer,
) -> Tuple[List[Dict[str, List[str]]], Dict[str, int]]:
    """Load prompts.json and convert to token-level examples."""
    prompts = load_prompts(data_path)
    label2id = build_label_lookup(prompts)

    examples = []
    for item in prompts:
        example = convert_prompt_to_example(item["prompt"], item["parts"], tokenizer)
        examples.append(example)

    return examples, label2id


def encode_example(example: Dict[str, List[str]], tokenizer, label2id: Dict[str, int]):
    tokens = example["tokens"]
    labels = example["labels"]

    if len(tokens) != len(labels):
        raise ValueError("Token and label lengths do not match.")

    token_ids = tokenizer.convert_tokens_to_ids(tokens)
    input_ids = tokenizer.build_inputs_with_special_tokens(token_ids)
    special_ids = set(tokenizer.all_special_ids)
    special_mask = [1 if token_id in special_ids else 0 for token_id in input_ids]
    attention_mask = [1] * len(input_ids)

    encoded_labels: List[int] = []
    label_idx = 0
    for is_special in special_mask:
        if is_special:
            encoded_labels.append(-100)
        else:
            encoded_labels.append(label2id[labels[label_idx]])
            label_idx += 1

    if label_idx != len(labels):
        raise ValueError("Did not assign all labels to tokens.")

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": encoded_labels,
    }


def tokenize_dataset(dataset: DatasetDict, tokenizer, label2id: Dict[str, int]) -> DatasetDict:
    return dataset.map(
        lambda x: encode_example(x, tokenizer, label2id),
        remove_columns=["tokens", "labels"],
    )


def count_token_matches(logits: torch.Tensor, labels: torch.Tensor) -> Tuple[int, int]:
    predictions = logits.argmax(dim=-1)
    mask = labels != -100
    correct = ((predictions == labels) & mask).sum().item()
    total = mask.sum().item()
    return correct, total


def evaluate_accuracy(model, dataloader: DataLoader, device: torch.device) -> float:
    was_training = model.training
    model.eval()
    correct_tokens = 0
    total_tokens = 0

    with torch.no_grad():
        for batch in dataloader:
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch)
            correct, total = count_token_matches(outputs.logits, batch["labels"])
            correct_tokens += correct
            total_tokens += total

    if was_training:
        model.train()

    return correct_tokens / total_tokens if total_tokens else 0.0


def classify_prompt(
    prompt: str,
    model,
    tokenizer,
    id2label: Dict[int, str],
) -> List[Tuple[str, str]]:
    prompt = prompt.strip()
    if not prompt:
        return []

    encoding = tokenizer(prompt, return_tensors="pt", truncation=True)
    tokens = tokenizer.convert_ids_to_tokens(encoding["input_ids"][0])
    encoding = {key: value.to(model.device) for key, value in encoding.items()}

    was_training = model.training
    model.eval()
    with torch.no_grad():
        outputs = model(**encoding)
    predictions = outputs.logits.argmax(dim=-1)[0].tolist()
    if was_training:
        model.train()

    special_tokens = set(tokenizer.all_special_tokens)
    results: List[Tuple[str, str]] = []
    for token, pred_id in zip(tokens, predictions):
        if token in special_tokens:
            continue
        results.append((token, id2label[int(pred_id)]))
    return normalize_task_predictions(results)


def main():
    set_seed(42)

    # Load tokenizer first (needed to convert prompts to token-level data)
    model_name = "distilbert-base-uncased"
    cache_dir = Path("./model_cache")
    cache_dir.mkdir(exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)

    # Load prompts and convert to token-level examples
    data_path = Path("prompts.json")
    examples, label2id = load_and_convert_prompts(data_path, tokenizer)
    id2label = {idx: label for label, idx in label2id.items()}

    raw_dataset = Dataset.from_list(examples)
    if len(raw_dataset) > 1:
        dataset_dict = raw_dataset.train_test_split(test_size=0.2, seed=42, shuffle=True)
    else:
        dataset_dict = DatasetDict(train=raw_dataset, test=raw_dataset)

    tokenized = tokenize_dataset(dataset_dict, tokenizer, label2id)

    collator = DataCollatorForTokenClassification(tokenizer)

    tokenized["train"].set_format(type="torch")
    tokenized["test"].set_format(type="torch")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id,
        cache_dir=cache_dir,
        dropout=0.2,
        attention_dropout=0.2,
    )
    model.to(device)

    train_loader = DataLoader(
        tokenized["train"], batch_size=16, shuffle=True, collate_fn=collator
    )
    val_loader = DataLoader(
        tokenized["test"], batch_size=16, shuffle=False, collate_fn=collator
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)

    num_epochs = 3
    global_step = 0
    patience = 20
    best_val_acc = 0.0
    steps_without_improvement = 0
    best_state_dict = None
    should_stop = False

    for epoch in range(num_epochs):
        for batch in train_loader:
            model.train()
            batch = {key: value.to(device) for key, value in batch.items()}

            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()

            optimizer.step()
            optimizer.zero_grad()

            correct, total = count_token_matches(outputs.logits.detach(), batch["labels"])
            train_accuracy = correct / total if total else 0.0

            val_accuracy = evaluate_accuracy(model, val_loader, device)
            global_step += 1

            print(
                f"epoch={epoch + 1} step={global_step} "
                f"train_loss={loss.item():.4f} train_acc={train_accuracy:.4f} "
                f"val_acc={val_accuracy:.4f}"
            )

            if val_accuracy > best_val_acc + 1e-4:
                best_val_acc = val_accuracy
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

    example_prompt = "yo check hows my heart doing then add a task to go to the rocket"
    predictions = classify_prompt(example_prompt, model, tokenizer, id2label)

    print("\nExample prompt classification:")
    print(example_prompt)
    print("Token predictions:")
    for word, label in predictions:
        print(f"  {word:<20} -> {label}")

    model.save_pretrained("outputs/final-model")
    tokenizer.save_pretrained("outputs/final-model")


if __name__ == "__main__":
    main()