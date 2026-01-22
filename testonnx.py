"""
Minimal inference script for the exported ONNX model.
"""

import json
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
from pathlib import Path

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def softmax(x, axis=-1):
    e_x = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e_x / e_x.sum(axis=axis, keepdims=True)

def main():
    model_dir = "model/outputs/simple-model"
    onnx_path = f"{model_dir}/model.onnx"
    
    if not Path(onnx_path).exists():
        print(f"Error: {onnx_path} not found. Run simpleonnx.py first.")
        return

    print("Loading ONNX model...")
    session = ort.InferenceSession(onnx_path)
    
    print("Loading tokenizer and labels...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    
    with open(f"{model_dir}/labels.json", "r") as f:
        labels = json.load(f)
        tool_labels = labels["tool_labels"]
        token_labels = labels["token_labels"]

    # Input
    text = "add a task to fix the engine"
    print(f"\nPrompt: {text}")
    
    inputs = tokenizer(text, return_tensors="np")
    # Cast to int64 for ONNX Runtime
    input_ids = inputs["input_ids"].astype(np.int64)
    attention_mask = inputs["attention_mask"].astype(np.int64)
    
    input_feed = {
        "input_ids": input_ids,
        "attention_mask": attention_mask
    }

    # Run inference
    # Outputs are: tag_logits, count_pred, token_logits
    outputs = session.run(None, input_feed)
    tag_logits = outputs[0][0]
    count_pred = outputs[1][0][0] # scalar
    token_logits = outputs[2][0]

    # Process Tags
    tag_probs = sigmoid(tag_logits)
    k = max(0, int(round(count_pred)))
    
    # Get top k tags if k > 0
    top_tags = []
    if k > 0:
        # get indices of top k
        top_indices = np.argsort(tag_probs)[-k:][::-1]
        top_tags = [tool_labels[i] for i in top_indices]
    
    print("\n--- Predictions ---")
    print(f"Count Pred: {count_pred:.2f} (k={k})")
    print(f"Predicted Tags: {top_tags}")
    
    # Process Tokens
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
    token_preds_indices = np.argmax(token_logits, axis=-1)
    
    print("\nToken Labels:")
    for tok, idx in zip(tokens, token_preds_indices):
        if tok not in ["[CLS]", "[SEP]", "[PAD]"]:
            label = token_labels[idx]
            print(f"  {tok:15} -> {label}")

if __name__ == "__main__":
    main()
