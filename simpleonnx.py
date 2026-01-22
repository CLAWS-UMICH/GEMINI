"""
Export the trained TwoHeadModel to ONNX format.
"""

import sys
import torch
import torch.nn as nn
import json
from pathlib import Path
from transformers import AutoModel, AutoTokenizer

# === REPLICATE MODEL ARCHITECTURE ===
# This must match simpletrain.py EXACTLY
class TwoHeadModel(nn.Module):
    """Embedding model with two linear heads."""

    def __init__(self, base_model: str, num_tools: int, num_token_labels: int, token_weights=None):
        super().__init__()
        # Enable output_hidden_states to access all layers
        self.encoder = AutoModel.from_pretrained(base_model, output_hidden_states=True)
        hidden = self.encoder.config.hidden_size
        self.num_tools = num_tools

        # Learnable weights for each layer (num_hidden_layers + 1 for embedding layer)
        n_layers = self.encoder.config.num_hidden_layers + 1
        self.layer_weights = nn.Parameter(torch.ones(n_layers))

        # Head 1: Overall tags from weighted [CLS] token
        self.tag_head = nn.Linear(hidden, num_tools)
        
        # Head 3: Predicting the number of tools (regression)
        self.count_head = nn.Linear(hidden, 1)

        # Head 2: Token-level classification
        self.token_head = nn.Sequential(
            nn.Linear(hidden, hidden * 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden * 2, hidden),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, num_token_labels)
        )

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
        weighted_cls = torch.sum(all_cls_tokens * norm_weights.view(-1, 1, 1), dim=0)

        tool_logits = self.tag_head(weighted_cls)  # (batch, num_tools)
        count_pred = self.count_head(weighted_cls) # (batch, 1)

        # All tokens for token-level (using last hidden state)
        last_hidden_state = out.last_hidden_state
        token_logits = self.token_head(last_hidden_state)  # (batch, seq, num_token_labels)

        return tool_logits, count_pred, token_logits


def export_to_onnx(model_dir: str = "model/outputs/simple-model", output_file: str = "model.onnx"):
    model_path = Path(model_dir)
    if not model_path.exists():
        print(f"Error: Model directory '{model_dir}' not found. Run simpletrain.py first.")
        return

    print(f"Loading model from {model_dir}...")
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Load metadata
    try:
        ckpt = torch.load(model_path / "model.pt", map_location=device)
    except FileNotFoundError:
         print(f"Error: 'model.pt' not found in {model_dir}")
         return

    tool_labels = ckpt["tool_labels"]
    token_labels = ckpt["token_labels"]
    
    # Check for new architecture key
    has_layer_weights = "layer_weights" in ckpt["model_state_dict"]
    
    # Initialize model
    model_name = "distilbert-base-uncased"
    
    if has_layer_weights:
        print("Detected NEW architecture (Weighted Hidden States).")
        model = TwoHeadModel(model_name, len(tool_labels), len(token_labels))
    else:
        print("Detected OLD architecture (Standard Embeddings).")
        # Define old class inline or patch the new one to behave like old
        # For simplicity, we just use the new class but we need to supply the missing weight
        # OR we define the old class here. Let's define a Legacy class to be safe.
        class LegacyTwoHeadModel(nn.Module):
            def __init__(self, base_model, num_tools, num_token_labels):
                super().__init__()
                self.encoder = AutoModel.from_pretrained(base_model)
                hidden = self.encoder.config.hidden_size
                self.tag_head = nn.Linear(hidden, num_tools)
                self.count_head = nn.Linear(hidden, 1)
                self.token_head = nn.Sequential(
                    nn.Linear(hidden, hidden * 2),
                    nn.GELU(),
                    nn.Dropout(0.1),
                    nn.Linear(hidden * 2, hidden),
                    nn.GELU(),
                    nn.Dropout(0.1),
                    nn.Linear(hidden, num_token_labels)
                )
                # Old model might have token_weights buffer
                self.register_buffer("token_weights", torch.ones(num_token_labels))

            def forward(self, input_ids, attention_mask, **kwargs):
                out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
                hidden_states = out.last_hidden_state
                cls = hidden_states[:, 0, :]
                tool_logits = self.tag_head(cls)
                count_pred = self.count_head(cls)
                token_logits = self.token_head(hidden_states)
                return tool_logits, count_pred, token_logits
        
        model = LegacyTwoHeadModel(model_name, len(tool_labels), len(token_labels))

    # Load weights
    # strict=False allows ignoring keys like 'token_weights' if they exist in ckpt but not in model, or vice versa
    # But for ONNX export correctness, we should be close.
    # The error showed "Unexpected key(s) in state_dict: 'token_weights'" for the new class
    # which means the old checkpoint HAS token_weights, but my new class didn't register it in __init__ properly (it had a check for None).
    
    model.load_state_dict(ckpt["model_state_dict"], strict=False)
    model.to(device)
    model.eval()

    # Create dummy input
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    text = "open the pod bay doors please"
    inputs = tokenizer(text, return_tensors="pt")
    input_ids = inputs["input_ids"].to(device)
    attention_mask = inputs["attention_mask"].to(device)

    # Output path
    out_path = model_path / output_file
    
    print("Exporting to ONNX...")
    
    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "tag_logits": {0: "batch_size"},
        "count_pred": {0: "batch_size"},
        "token_logits": {0: "batch_size", 1: "sequence_length"}
    }

    torch.onnx.export(
        model,
        (input_ids, attention_mask),
        str(out_path),
        export_params=True,
        opset_version=14, 
        do_constant_folding=True,
        input_names=["input_ids", "attention_mask"],
        output_names=["tag_logits", "count_pred", "token_logits"],
        dynamic_axes=dynamic_axes,
    )

    print(f"Successfully exported model to {out_path}")
    
    try:
        import onnx
        onnx_model = onnx.load(str(out_path))
        onnx.checker.check_model(onnx_model)
        print("ONNX model checked and valid.")
    except ImportError:
        pass
    except Exception as e:
        print(f"ONNX verification failed: {e}")

if __name__ == "__main__":
    export_to_onnx()
