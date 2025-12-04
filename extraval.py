"""Evaluate the fine-tuned model on extraval.json at the semantic level.

Checks:
1. Were the correct tools/actions called? (GET_VITALS, CREATE_TASK, NAVIGATION_QUERY)
2. If CREATE_TASK, are the extracted task names correct?
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from decoding import decode_predictions, normalize_task_predictions


def load_prompts(data_path: Path) -> List[Dict]:
    """Load the prompts JSON file."""
    with data_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_expected_from_parts(parts: List[Dict]) -> Tuple[Set[str], List[str]]:
    """Extract expected tools and task names from labeled parts.
    
    Returns:
        (expected_tools, expected_task_names)
    """
    tools: Set[str] = set()
    task_name_parts: List[str] = []
    task_names: List[str] = []
    in_task_name = False

    for part in parts:
        label = part["type"]
        text = part["text"]

        if label in ("GET_VITALS", "CREATE_TASK", "NAVIGATION_QUERY"):
            tools.add(label)

        if label == "TASK_NAME_START":
            # Start a new task name
            if in_task_name and task_name_parts:
                task_names.append("".join(task_name_parts).strip())
            task_name_parts = [text]
            in_task_name = True
        elif label == "TASK_NAME_CONT":
            if in_task_name:
                task_name_parts.append(text)
            else:
                # Treat as start if not already in task name
                task_name_parts = [text]
                in_task_name = True
        else:
            if in_task_name and task_name_parts:
                task_names.append("".join(task_name_parts).strip())
                task_name_parts = []
            in_task_name = False

    # Finish any remaining task name
    if task_name_parts:
        task_names.append("".join(task_name_parts).strip())

    return tools, task_names


def classify_prompt(
    prompt: str,
    model,
    tokenizer,
    id2label: Dict[int, str],
) -> List[Tuple[str, str]]:
    """Classify a prompt and return token-level predictions."""
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


def extract_predicted_tools(predictions: List[Tuple[str, str]]) -> Set[str]:
    """Extract which tools were predicted."""
    tools: Set[str] = set()
    for _, label in predictions:
        if label in ("GET_VITALS", "CREATE_TASK", "NAVIGATION_QUERY"):
            tools.add(label)
    return tools


def normalize_task_name(name: str) -> str:
    """Normalize task name for comparison (lowercase, collapsed whitespace)."""
    return " ".join(name.lower().split())


def main():
    model_path = Path("outputs/final-model")
    data_path = Path("extraval.json")

    print("=" * 70)
    print("EXTRAVAL - Semantic Evaluation")
    print("=" * 70)
    print(f"\nModel: {model_path}")
    print(f"Data:  {data_path}\n")

    # Load model and tokenizer
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForTokenClassification.from_pretrained(model_path)
    model.to(device)
    model.eval()

    id2label = model.config.id2label

    # Load validation data
    prompts = load_prompts(data_path)
    print(f"Loaded {len(prompts)} validation prompts\n")

    # Stats
    tools_correct = 0
    task_names_correct = 0
    task_names_applicable = 0
    fully_correct = 0

    print("-" * 70)
    print("DETAILED RESULTS")
    print("-" * 70)

    for i, item in enumerate(prompts):
        prompt = item["prompt"]
        parts = item["parts"]

        # Get expected
        expected_tools, expected_task_names = extract_expected_from_parts(parts)

        # Get predicted
        predictions = classify_prompt(prompt, model, tokenizer, id2label)
        decoded = decode_predictions(predictions)
        predicted_tools = extract_predicted_tools(predictions)
        predicted_task_names = decoded["task_names"]

        # Evaluate tools
        tools_match = expected_tools == predicted_tools

        # Evaluate task names (if applicable)
        has_task_names = len(expected_task_names) > 0
        names_match = True
        if has_task_names:
            task_names_applicable += 1
            expected_normalized = [normalize_task_name(n) for n in expected_task_names]
            predicted_normalized = [normalize_task_name(n) for n in predicted_task_names]
            names_match = expected_normalized == predicted_normalized
            if names_match:
                task_names_correct += 1

        if tools_match:
            tools_correct += 1

        is_fully_correct = tools_match and names_match
        if is_fully_correct:
            fully_correct += 1

        # Log this prompt
        status = "✓" if is_fully_correct else "✗"
        print(f"\n[{i+1}] {status} \"{prompt}\"")

        # Tools comparison
        if tools_match:
            print(f"    Tools: ✓ {sorted(expected_tools)}")
        else:
            print(f"    Tools: ✗")
            print(f"      Expected:  {sorted(expected_tools)}")
            print(f"      Predicted: {sorted(predicted_tools)}")

        # Task names comparison (if applicable)
        if has_task_names:
            if names_match:
                print(f"    Task names: ✓ {expected_task_names}")
            else:
                print(f"    Task names: ✗")
                print(f"      Expected:  {expected_task_names}")
                print(f"      Predicted: {predicted_task_names}")

    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    tools_acc = 100 * tools_correct / len(prompts) if prompts else 0
    full_acc = 100 * fully_correct / len(prompts) if prompts else 0

    print(f"\nTools Correct:      {tools_correct}/{len(prompts)} ({tools_acc:.1f}%)")

    if task_names_applicable > 0:
        names_acc = 100 * task_names_correct / task_names_applicable
        print(f"Task Names Correct: {task_names_correct}/{task_names_applicable} ({names_acc:.1f}%)")
    else:
        print(f"Task Names Correct: N/A (no prompts with task names)")

    print(f"\nFully Correct:      {fully_correct}/{len(prompts)} ({full_acc:.1f}%)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
