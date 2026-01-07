from __future__ import annotations

from pathlib import Path

import torch

from finetune import MultiTaskModel, TOOL_LABELS
from decoding import decode_predictions


def load_model(model_dir: Path):
    """Load the trained multi-task model."""
    from transformers import AutoTokenizer

    checkpoint = torch.load(model_dir / "model.pt", map_location="cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    model = MultiTaskModel(
        base_model_name="distilbert-base-uncased",
        num_token_labels=len(checkpoint['label2id']),
        num_tool_labels=len(checkpoint['tool_labels']),
        use_crf=checkpoint.get('use_crf', False),  # Backwards compatible
    )
    model.load_state_dict(checkpoint['model_state_dict'])

    return model, tokenizer, checkpoint['id2label']


def classify_prompt(prompt: str, model, tokenizer, id2label):
    """Classify prompt for tool calls and task names."""
    prompt = prompt.strip()
    if not prompt:
        return [], []

    encoding = tokenizer(prompt, return_tensors="pt", truncation=True)
    tokens = tokenizer.convert_ids_to_tokens(encoding["input_ids"][0])

    model.eval()
    with torch.no_grad():
        outputs = model(**encoding)

    # Tool predictions (from CLS token)
    tool_probs = torch.sigmoid(outputs["tool_logits"][0])
    predicted_tools = [TOOL_LABELS[i] for i, prob in enumerate(tool_probs) if prob > 0.5]

    # Token predictions (use CRF Viterbi if available)
    if model.use_crf:
        mask = torch.ones(outputs["token_emissions"].shape[:2], dtype=torch.uint8)
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


def main():
    model_dir = Path("outputs/final-model")
    if not model_dir.exists():
        raise SystemExit("Trained model not found. Run finetune.py first.")

    print("Loading model...")
    model, tokenizer, id2label = load_model(model_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    print("Multi-task classifier ready. Type text or 'quit' to exit.")
    print("Model predicts: (1) Tool calls from CLS token, (2) Task names from tokens\n")

    while True:
        try:
            user_input = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            break

        # Get predictions
        tools, token_preds = classify_prompt(user_input, model, tokenizer, id2label)

        # Display tool calls
        if tools:
            print(f"Tool calls: {', '.join(tools)}")
        else:
            print("Tool calls: (none)")

        # Display token classifications
        if not token_preds:
            print("(No tokens)")
            continue

        longest_word = max(len(word) for word, _ in token_preds)
        print("\nToken classifications:")
        for word, label in token_preds:
            print(f"  {word.ljust(longest_word)} -> {label}")

        # Extract task names
        decoded = decode_predictions(token_preds)
        if decoded["task_names"]:
            print(f"\nTask names extracted: {decoded['task_names']}")
        else:
            print("\nTask names extracted: (none)")

        print()  # Blank line


if __name__ == "__main__":
    main()
