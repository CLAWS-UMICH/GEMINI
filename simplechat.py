"""
Interactive chat to test the trained two-head model.
"""

import torch
import torch.nn as nn
from pathlib import Path
from transformers import AutoModel, AutoTokenizer


class TwoHeadModel(nn.Module):
    """Embedding model with two linear heads."""

    def __init__(self, base_model: str, num_tag_outputs: int, num_token_labels: int, token_weights=None):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = self.encoder.config.hidden_size
        self.tag_head = nn.Linear(hidden, num_tag_outputs)
        self.count_head = nn.Linear(hidden, 1)
        self.token_head = nn.Linear(hidden, num_token_labels)
        # Placeholder for class weights (loaded from state dict)
        if token_weights is not None:
            self.register_buffer("token_weights", token_weights)
        else:
            self.register_buffer("token_weights", torch.ones(num_token_labels))

    def forward(self, input_ids, attention_mask, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        hidden_states = out.last_hidden_state
        cls = hidden_states[:, 0, :]
        tag_logits = self.tag_head(cls)
        count_pred = self.count_head(cls)
        token_logits = self.token_head(hidden_states)
        return {"tag_logits": tag_logits, "count_pred": count_pred, "token_logits": token_logits}


def load_model(model_dir: str = "trainedmodel/outputs/simple-model"):
    model_dir = Path(model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load checkpoint
    ckpt = torch.load(model_dir / "model.pt", map_location=device)
    tool_labels = ckpt["tool_labels"]
    token_labels = ckpt["token_labels"]
    tool_labels = ckpt["tool_labels"]
    token_labels = ckpt["token_labels"]
    num_tag_outputs = len(tool_labels)
    # has_threshold check removed as usage changed

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    # Rebuild model
    model = TwoHeadModel("distilbert-base-uncased", num_tag_outputs, len(token_labels))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device)
    model.eval()

    return model, tokenizer, tool_labels, token_labels, device


def classify(prompt: str, model, tokenizer, tool_labels, token_labels, device):
    """Classify a prompt and return results."""
    # Normalize prompt
    prompt = prompt.lower()
    
    enc = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128)
    enc = {k: v.to(device) for k, v in enc.items()}
    tokens = tokenizer.convert_ids_to_tokens(enc["input_ids"][0])

    with torch.no_grad():
        out = model(**enc)

    # Tags
    # Tags
    tag_logits = out["tag_logits"][0]
    count_pred = out["count_pred"][0].item()
    
    import math
    k = int(math.floor(count_pred))
    k = max(0, k)
    
    tag_probs = torch.sigmoid(tag_logits)
    
    pred_tags = []
    if k > 0:
        _, top_indices = torch.topk(tag_probs, k)
        pred_tags = [(tool_labels[i], f"{tag_probs[i]:.2f}") for i in top_indices.tolist()]
        
    all_tags = [(tool_labels[i], f"{p:.2f}") for i, p in enumerate(tag_probs)]

    # Tokens
    token_preds = out["token_logits"].argmax(dim=-1)[0]
    token_results = []
    for tok, pred in zip(tokens, token_preds):
        if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
            token_results.append((tok, token_labels[pred.item()]))

    return pred_tags, all_tags, token_results, count_pred, k


def format_token_output(token_results):
    """Format tokens with colors based on label."""
    colors = {
        "TEXT": "\033[90m",           # gray
        "TASK_NAME_START": "\033[92m", # green
        "TASK_NAME_CONT": "\033[93m",  # yellow
    }
    reset = "\033[0m"

    formatted = []
    for tok, label in token_results:
        # Clean up subword tokens
        display_tok = tok.replace("##", "")
        color = colors.get(label, "")
        formatted.append(f"{color}{display_tok}{reset}")

    return " ".join(formatted)


def main():
    print("Loading model...")
    try:
        model, tokenizer, tool_labels, token_labels, device = load_model()
    except FileNotFoundError:
        print("Model not found! Run simpletrain.py first.")
        return

    print(f"Model loaded on {device}")
    print(f"Tool labels: {tool_labels}")
    print(f"Token labels: {token_labels}")
    print("\n" + "=" * 60)
    print("Type a prompt to classify. Type 'quit' to exit.")
    print("=" * 60 + "\n")

    while True:
        try:
            prompt = input("\033[96mYou:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not prompt:
            continue
        if prompt.lower() in ["quit", "exit", "q"]:
            print("Bye!")
            break

        pred_tags, all_tags, token_results, count_pred, k = classify(
            prompt, model, tokenizer, tool_labels, token_labels, device
        )

        print()
        print("\033[95mTags:\033[0m", end=" ")
        if pred_tags:
            print(", ".join(f"{t} ({p})" for t, p in pred_tags))
        else:
            print("(none)")

            print("(none)")

        print("\033[95mCount Pred:\033[0m", f"{count_pred:.2f} (k={k})")
        # print("\033[95mAll scores:\033[0m", ", ".join(f"{t}: {p}" for t, p in all_tags))

        print("\033[95mTokens:\033[0m", format_token_output(token_results))

        # Also show raw breakdown
        print("\033[95mBreakdown:\033[0m")
        for tok, label in token_results:
            marker = ""
            if label == "TASK_NAME_START":
                marker = " ← START"
            elif label == "TASK_NAME_CONT":
                marker = " ← CONT"
            print(f"  {tok:20} {label}{marker}")

        print()


if __name__ == "__main__":
    main()
