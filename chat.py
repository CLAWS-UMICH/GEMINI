from __future__ import annotations

from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from finetune import classify_prompt
from decoding import decode_predictions


def main():
    model_dir = Path("outputs/final-model")
    if not model_dir.exists():
        raise SystemExit("Trained artifacts not found. Run finetune.py first.")

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    id2label = {int(idx): label for idx, label in model.config.id2label.items()}

    print("Token chat classifier. Type text to classify or 'quit' to exit.")
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

        predictions = classify_prompt(user_input, model, tokenizer, id2label)
        if not predictions:
            print("(No tokens)")
            continue

        longest_word = max(len(word) for word, _ in predictions)
        print("Token classifications:")
        for word, label in predictions:
            print(f"  {word.ljust(longest_word)} -> {label}")

        decoded = decode_predictions(predictions)
        tools = []
        if decoded["get_vitals"]:
            tools.append("GET_VITALS")
        if decoded["create_task"]:
            tools.append("CREATE_TASK")
        if any(label == "NAVIGATION_QUERY" for _, label in predictions):
            tools.append("NAVIGATION_QUERY")

        print(f"Tool calls: {', '.join(tools) if tools else '(none)'}")
        if decoded["task_names"]:
            print(f"Task names: {decoded['task_names']}")


if __name__ == "__main__":
    main()

