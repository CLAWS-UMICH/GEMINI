"""Evaluate the fine-tuned multi-task model on extraval_data.json.

NEW MULTI-TASK ARCHITECTURE:
- Sequence classification (CLS token): Predict tool calls
- Token classification: Extract task names

Evaluates:
1. Tool call prediction accuracy
2. Task name extraction accuracy
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import torch

from finetune import MultiTaskModel, TOOL_LABELS
from decoding import decode_predictions


def load_prompts(data_path: Path) -> List[Dict]:
    """Load the prompts JSON file."""
    with data_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_expected_task_names(parts: List[Dict]) -> List[str]:
    """Extract expected task names from labeled parts."""
    task_name_parts: List[str] = []
    task_names: List[str] = []
    in_task_name = False

    for part in parts:
        label = part["type"]
        text = part["text"]

        if label == "TASK_NAME_START":
            if in_task_name and task_name_parts:
                task_names.append("".join(task_name_parts).strip())
            task_name_parts = [text]
            in_task_name = True
        elif label == "TASK_NAME_CONT":
            if in_task_name:
                task_name_parts.append(text)
            else:
                task_name_parts = [text]
                in_task_name = True
        else:
            if in_task_name and task_name_parts:
                task_names.append("".join(task_name_parts).strip())
                task_name_parts = []
            in_task_name = False

    if task_name_parts:
        task_names.append("".join(task_name_parts).strip())

    return task_names


def classify_prompt(prompt: str, model, tokenizer, id2label):
    """Classify a prompt for both tool calls and task names."""
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
        mask = torch.ones(outputs["token_emissions"].shape[:2], dtype=torch.uint8, device=model.bert.device)
        best_paths = model.crf.decode(outputs["token_emissions"], mask)
        token_preds = best_paths[0]
    else:
        token_preds = outputs["token_logits"].argmax(dim=-1)[0].tolist()

    special_tokens = set(tokenizer.all_special_tokens)
    token_results = []
    for token, pred_id in zip(tokens, token_preds):
        if token in special_tokens:
            continue
        token_results.append((token, id2label[int(pred_id)]))

    return predicted_tools, token_results


def normalize_task_name(name: str) -> str:
    """Normalize task name for comparison (lowercase, collapsed whitespace)."""
    return " ".join(name.lower().split())


def main():
    model_dir = Path("outputs/final-model")
    data_path = Path("extraval_data.json")

    print("=" * 70)
    print("EXTRAVAL - Multi-Task Semantic Evaluation")
    print("=" * 70)
    print(f"\nModel: {model_dir}")
    print(f"Data:  {data_path}\n")

    # Load model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    from transformers import AutoTokenizer

    checkpoint = torch.load(model_dir / "model.pt", map_location=device)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    model = MultiTaskModel(
        base_model_name="distilbert-base-uncased",
        num_token_labels=len(checkpoint['label2id']),
        num_tool_labels=len(checkpoint['tool_labels']),
        use_crf=checkpoint.get('use_crf', False),
    )
    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)
    model.eval()

    id2label = checkpoint['id2label']

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
        expected_tools = set(item.get("tool_calls", []))

        # Get expected task names
        expected_task_names = extract_expected_task_names(parts)

        # Get predictions
        predicted_tools, token_preds = classify_prompt(prompt, model, tokenizer, id2label)
        predicted_tools_set = set(predicted_tools)

        decoded = decode_predictions(token_preds)
        predicted_task_names = decoded["task_names"]

        # Evaluate tools
        tools_match = expected_tools == predicted_tools_set

        # Evaluate task names
        has_task_names = len(expected_task_names) > 0
        names_match = True
        if has_task_names:
            task_names_applicable += 1
            expected_normalized = [normalize_task_name(n) for n in expected_task_names]
            predicted_normalized = [normalize_task_name(n) for n in predicted_task_names]
            names_match = expected_normalized == predicted_normalized
            if names_match:
                task_names_correct += 1
        else:
            # No expected task names
            names_match = len(predicted_task_names) == 0

        if tools_match:
            tools_correct += 1

        is_fully_correct = tools_match and names_match
        if is_fully_correct:
            fully_correct += 1

        # Log this prompt
        status = "PASS" if is_fully_correct else "FAIL"
        print(f"\n[{i+1}] {status} \"{prompt}\"")

        # Tools comparison
        if tools_match:
            print(f"    Tools: OK {sorted(expected_tools)}")
        else:
            print(f"    Tools: MISMATCH")
            print(f"      Expected:  {sorted(expected_tools)}")
            print(f"      Predicted: {sorted(predicted_tools_set)}")

        # Task names comparison
        if has_task_names:
            if names_match:
                print(f"    Task names: OK {expected_task_names}")
            else:
                print(f"    Task names: MISMATCH")
                print(f"      Expected:  {expected_task_names}")
                print(f"      Predicted: {predicted_task_names}")
        else:
            if not predicted_task_names:
                print(f"    Task names: OK (none)")
            else:
                print(f"    Task names: MISMATCH (predicted {predicted_task_names} but expected none)")

    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    tools_acc = 100 * tools_correct / len(prompts) if prompts else 0
    print(f"\nTools Correct:      {tools_correct}/{len(prompts)} ({tools_acc:.1f}%)")

    if task_names_applicable > 0:
        names_acc = 100 * task_names_correct / task_names_applicable
        print(f"Task Names Correct: {task_names_correct}/{task_names_applicable} ({names_acc:.1f}%)")
    else:
        print(f"Task Names Correct: N/A (no prompts with task names)")

    full_acc = 100 * fully_correct / len(prompts) if prompts else 0
    print(f"\nFully Correct:      {fully_correct}/{len(prompts)} ({full_acc:.1f}%)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
