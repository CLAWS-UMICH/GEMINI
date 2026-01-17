"""
Evaluate the trained model on simpleevals.json and log detailed metrics.
"""

import json
import torch
import torch.nn as nn
from pathlib import Path
from collections import defaultdict
from transformers import AutoModel, AutoTokenizer


# Labels - loaded dynamically from the model checkpoint
TOOL_LABELS = []
TOKEN_LABELS = []


class TwoHeadModel(nn.Module):
    def __init__(self, base_model: str, num_tag_outputs: int, num_token_labels: int, token_weights=None):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = self.encoder.config.hidden_size
        self.tag_head = nn.Linear(hidden, num_tag_outputs)
        self.token_head = nn.Linear(hidden, num_token_labels)
        if token_weights is not None:
            self.register_buffer("token_weights", token_weights)
        else:
            self.register_buffer("token_weights", torch.ones(num_token_labels))

    def forward(self, input_ids, attention_mask, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        hidden_states = out.last_hidden_state
        cls = hidden_states[:, 0, :]
        tag_logits = self.tag_head(cls)
        token_logits = self.token_head(hidden_states)
        return {"tag_logits": tag_logits, "token_logits": token_logits}


def load_model(model_dir="model/outputs/simple-model"):
    global TOOL_LABELS, TOKEN_LABELS
    
    model_dir = Path(model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    ckpt = torch.load(model_dir / "model.pt", map_location=device)
    TOOL_LABELS = ckpt["tool_labels"]
    TOKEN_LABELS = ckpt["token_labels"]
    num_tag_outputs = ckpt["model_state_dict"]["tag_head.weight"].shape[0]
    has_threshold = num_tag_outputs == (len(TOOL_LABELS) + 1)

    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    model = TwoHeadModel("distilbert-base-uncased", num_tag_outputs, len(TOKEN_LABELS))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()

    return model, tokenizer, device, has_threshold


def load_eval_data(path="simpleevals.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def classify(prompt, model, tokenizer, device, has_threshold):
    """Get predictions for a single prompt."""
    enc = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    enc = {k: v.to(device) for k, v in enc.items()}
    tokens = tokenizer.convert_ids_to_tokens(enc["input_ids"][0])

    with torch.no_grad():
        out = model(**enc)

    # Tags
    tag_logits = out["tag_logits"][0]
    if has_threshold:
        tool_logits = tag_logits[: len(TOOL_LABELS)]
        threshold = torch.sigmoid(tag_logits[len(TOOL_LABELS)]).item()
    else:
        tool_logits = tag_logits
        threshold = 0.5
    tag_probs = torch.sigmoid(tool_logits)
    pred_tags = [TOOL_LABELS[i] for i, p in enumerate(tag_probs) if p > threshold]

    # Tokens
    token_preds = out["token_logits"].argmax(dim=-1)[0]
    token_results = []
    for tok, pred in zip(tokens, token_preds):
        if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
            token_results.append((tok, TOKEN_LABELS[pred.item()]))

    return pred_tags, token_results


def get_ground_truth_tokens(prompt, parts, tokenizer):
    """Convert parts to token-level labels matching model's tokenization."""
    # Build char-level labels
    char_labels = []
    for part in parts:
        char_labels.extend([part["type"]] * len(part["text"]))

    enc = tokenizer(prompt, return_offsets_mapping=True, truncation=True, max_length=128)
    offsets = enc["offset_mapping"]
    tokens = tokenizer.convert_ids_to_tokens(enc["input_ids"])

    token_results = []
    for tok, (start, end) in zip(tokens, offsets):
        if tok in ["[CLS]", "[SEP]", "[PAD]"]:
            continue
        if start < len(char_labels):
            token_results.append((tok, char_labels[start]))
        else:
            token_results.append((tok, "TEXT"))

    return token_results


def evaluate(model, tokenizer, device, eval_data, has_threshold):
    """Run full evaluation and return metrics."""
    results = {
        "total": len(eval_data),
        "tag_exact_match": 0,
        "tag_partial_match": 0,
        "token_accuracy": 0,
        "task_name_precision": 0,
        "task_name_recall": 0,
        "details": [],
    }

    # Per-tool metrics
    tool_metrics = {t: {"tp": 0, "fp": 0, "fn": 0} for t in TOOL_LABELS}

    # Token-level confusion
    token_confusion = defaultdict(lambda: defaultdict(int))

    total_tokens = 0
    correct_tokens = 0
    task_name_pred_count = 0
    task_name_true_count = 0
    task_name_correct = 0

    for item in eval_data:
        prompt = item["prompt"]
        true_tags = set(item["tool_calls"])
        parts = item["parts"]

        pred_tags, pred_tokens = classify(prompt, model, tokenizer, device, has_threshold)
        true_tokens = get_ground_truth_tokens(prompt, parts, tokenizer)

        pred_tags_set = set(pred_tags)

        # Tag metrics
        exact_match = pred_tags_set == true_tags
        if exact_match:
            results["tag_exact_match"] += 1

        # Partial match (any overlap)
        if pred_tags_set & true_tags:
            results["tag_partial_match"] += 1

        # Per-tool TP/FP/FN
        for tool in TOOL_LABELS:
            if tool in true_tags and tool in pred_tags_set:
                tool_metrics[tool]["tp"] += 1
            elif tool in pred_tags_set and tool not in true_tags:
                tool_metrics[tool]["fp"] += 1
            elif tool in true_tags and tool not in pred_tags_set:
                tool_metrics[tool]["fn"] += 1

        # Token metrics
        for (pred_tok, pred_label), (true_tok, true_label) in zip(pred_tokens, true_tokens):
            total_tokens += 1
            if pred_label == true_label:
                correct_tokens += 1

            token_confusion[true_label][pred_label] += 1

            # Task name extraction (START or CONT)
            is_task_name_true = true_label in ["TASK_NAME_START", "TASK_NAME_CONT"]
            is_task_name_pred = pred_label in ["TASK_NAME_START", "TASK_NAME_CONT"]

            if is_task_name_true:
                task_name_true_count += 1
            if is_task_name_pred:
                task_name_pred_count += 1
            if is_task_name_true and is_task_name_pred:
                task_name_correct += 1

        # Log detail
        results["details"].append({
            "prompt": prompt,
            "true_tags": list(true_tags),
            "pred_tags": pred_tags,
            "tag_correct": exact_match,
            "tokens": [
                {
                    "token": pred_tok,
                    "pred": pred_label,
                    "true": true_label,
                    "correct": pred_label == true_label,
                }
                for (pred_tok, pred_label), (_, true_label) in zip(pred_tokens, true_tokens)
            ],
        })

    # Calculate final metrics
    results["token_accuracy"] = correct_tokens / total_tokens if total_tokens > 0 else 0
    results["task_name_precision"] = task_name_correct / task_name_pred_count if task_name_pred_count > 0 else 0
    results["task_name_recall"] = task_name_correct / task_name_true_count if task_name_true_count > 0 else 0

    # F1 for task names
    p, r = results["task_name_precision"], results["task_name_recall"]
    results["task_name_f1"] = 2 * p * r / (p + r) if (p + r) > 0 else 0

    # Per-tool precision/recall
    results["per_tool"] = {}
    for tool in TOOL_LABELS:
        m = tool_metrics[tool]
        precision = m["tp"] / (m["tp"] + m["fp"]) if (m["tp"] + m["fp"]) > 0 else 0
        recall = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        results["per_tool"][tool] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": m["tp"] + m["fn"],
        }

    results["token_confusion"] = {k: dict(v) for k, v in token_confusion.items()}

    return results


def print_results(results):
    """Pretty print evaluation results."""
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    print(f"\nTotal examples: {results['total']}")

    print("\n--- TAG CLASSIFICATION ---")
    print(f"Exact match accuracy: {results['tag_exact_match']}/{results['total']} ({100*results['tag_exact_match']/results['total']:.1f}%)")
    print(f"Partial match (any correct): {results['tag_partial_match']}/{results['total']} ({100*results['tag_partial_match']/results['total']:.1f}%)")

    print("\nPer-tool metrics:")
    print(f"  {'Tool':<20} {'Prec':>8} {'Recall':>8} {'F1':>8} {'Support':>8}")
    print("  " + "-" * 52)
    for tool, m in results["per_tool"].items():
        print(f"  {tool:<20} {m['precision']:>8.2f} {m['recall']:>8.2f} {m['f1']:>8.2f} {m['support']:>8}")

    print("\n--- TOKEN CLASSIFICATION ---")
    print(f"Overall accuracy: {100*results['token_accuracy']:.1f}%")
    print(f"Task name precision: {100*results['task_name_precision']:.1f}%")
    print(f"Task name recall: {100*results['task_name_recall']:.1f}%")
    print(f"Task name F1: {100*results['task_name_f1']:.1f}%")

    print("\nConfusion matrix (true \\ pred):")
    labels = TOKEN_LABELS
    print(f"  {'':>18}", end="")
    for l in labels:
        print(f" {l[:8]:>10}", end="")
    print()

    confusion = results["token_confusion"]
    for true_label in labels:
        print(f"  {true_label:>18}", end="")
        for pred_label in labels:
            count = confusion.get(true_label, {}).get(pred_label, 0)
            print(f" {count:>10}", end="")
        print()

    # Show some failures
    print("\n--- SAMPLE FAILURES ---")
    failures = [d for d in results["details"] if not d["tag_correct"]]
    for fail in failures[:5]:
        print(f"\n  Prompt: {fail['prompt']}")
        print(f"  True: {fail['true_tags']}")
        print(f"  Pred: {fail['pred_tags']}")

    # Token failures
    print("\n--- TOKEN EXTRACTION ERRORS ---")
    for d in results["details"][:10]:
        errors = [t for t in d["tokens"] if not t["correct"]]
        if errors:
            print(f"\n  Prompt: {d['prompt']}")
            for e in errors:
                print(f"    '{e['token']}': expected {e['true']}, got {e['pred']}")


def main():
    print("Loading model...")
    try:
        model, tokenizer, device, has_threshold = load_model()
    except FileNotFoundError:
        print("Model not found! Run simpletrain.py first.")
        return

    print(f"Model loaded on {device}")

    print("Loading eval data...")
    eval_data = load_eval_data()
    print(f"Loaded {len(eval_data)} eval examples")

    print("Running evaluation...")
    results = evaluate(model, tokenizer, device, eval_data, has_threshold)

    print_results(results)

    # Save full results
    out_path = Path("outputs/eval_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()

