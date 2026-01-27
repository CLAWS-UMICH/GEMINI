"""
AI Response Training Script for FunctionGemma (causal LM).

Trains a model to generate the final natural-language assistant response given:
- User's original query
- Tool calls that were made
- Results from those tool calls

IMPORTANT:
We use FunctionGemma's official Hugging Face chat template formatting via:
    tokenizer.apply_chat_template(..., tools=..., ...)

This is the least error-prone way to ensure:
- correct <start_of_turn> / <end_of_turn>
- correct <start_function_declaration> blocks for tools
- correct <start_function_call> for tool calls
- correct <start_function_response> for tool results
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from google.colab import userdata
import torch
from torch.utils.data import Dataset, DataLoader, random_split
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
)

# Import data loader from existing module
from simpledatacombine import load_all_training_data


# =============================================================================
# Configuration - Edit these to change behavior
# =============================================================================

MODEL_NAME = "google/functiongemma-270m-it"
OUTPUT_DIR = "functiongemma_ai_response_model"

# FunctionGemma prompts are longer due to tool declarations + control tokens
MAX_SEQ_LENGTH = 1024
BATCH_SIZE = 8

# Training settings
EPOCHS = 10
BASE_LR = 5e-5
WEIGHT_DECAY = 0.01
WARMUP_EPOCHS = 2
MAX_GRAD_NORM = 1.0
PATIENCE = 5

# Set to True to just show sample formatted data without training
DRY_RUN = False

# Device - just use cuda
DEVICE = torch.device("cuda")

# Essential FunctionGemma developer prompt (do not change lightly)
FUNCTIONGEMMA_DEVELOPER_MSG = "You are a model that can do function calling with the following functions"


# =============================================================================
# Helper functions for FunctionGemma message/tool shaping
# =============================================================================

def _infer_json_schema_type(v: Any) -> str:
    """Map python values to JSON schema type strings."""
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "string"


def _normalize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """
    Normalize dataset tool_calls into FunctionGemma/HF format:
        [{"type":"function","function":{"name":..., "arguments": {...}}}, ...]
    Supports:
      - list[str] tool names
      - list[dict] like {"name":..., "arguments":...}
      - list already in HF tool_calls shape
    """
    if not tool_calls:
        return []

    out = []
    for tc in tool_calls:
        # Already in HF tool_calls format?
        if isinstance(tc, dict) and tc.get("type") == "function" and isinstance(tc.get("function"), dict):
            fn = tc["function"]
            out.append({
                "type": "function",
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", {}) or {},
                }
            })
            continue

        # Dict shorthand: {"name": ..., "arguments": ...}
        if isinstance(tc, dict) and "name" in tc:
            out.append({
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc.get("arguments", {}) or {},
                }
            })
            continue

        # String tool name
        if isinstance(tc, str):
            out.append({
                "type": "function",
                "function": {"name": tc, "arguments": {}}
            })
            continue

        raise ValueError(f"Unsupported tool call shape: {tc!r}")

    return out


def _normalize_tool_results(tool_calls_hf: List[Dict[str, Any]], results: Any) -> List[Dict[str, Any]]:
    """
    Normalize tool execution results into the FunctionGemma tool role content:
        [{"name": <tool_name>, "response": <dict>}, ...]
    Docs recommend this shape for best chat_template results.
    """
    if not results:
        return []

    # If results is already in the recommended list[{"name","response"}] shape:
    if isinstance(results, list) and all(isinstance(r, dict) and "name" in r and "response" in r for r in results):
        return results

    # If results is a dict with {"name","response"}:
    if isinstance(results, dict) and "name" in results and "response" in results:
        return [results]

    # Otherwise, assume it aligns positionally to tool_calls
    # Common in your existing data: results=[{"intent": "...", "return": ...}, ...]
    if not isinstance(results, list):
        results = [results]

    normalized = []
    for i, r in enumerate(results):
        tool_name = tool_calls_hf[i]["function"]["name"] if i < len(tool_calls_hf) else "unknown_tool"
        if isinstance(r, dict):
            resp_obj = r
        else:
            resp_obj = {"return": r}
        normalized.append({"name": tool_name, "response": resp_obj})

    return normalized


def _build_tools_schema(tool_calls_hf: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build a minimal tools schema list for tokenizer.apply_chat_template(..., tools=...).

    Shape matches HF "tools" list:
      [{"type":"function","function":{"name":..., "description":..., "parameters": {...}}}, ...]

    If arguments are present, we infer parameter names/types; otherwise parameters is empty object.
    """
    tools = []
    seen = set()

    for tc in tool_calls_hf:
        fn = tc["function"]
        name = fn["name"]
        if not name or name in seen:
            continue
        seen.add(name)

        args = fn.get("arguments", {}) or {}
        properties = {}
        required = []

        if isinstance(args, dict) and args:
            for k, v in args.items():
                properties[k] = {
                    "type": _infer_json_schema_type(v),
                    "description": f"Autogenerated parameter: {k}",
                }
                required.append(k)

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Autogenerated tool schema for {name}.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        })

    return tools


def _build_messages_for_example(prompt: str,
                                tool_calls: Any,
                                results: Any,
                                include_final_assistant: bool,
                                final_assistant_text: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Construct (messages, tools) in the exact structure expected by FunctionGemma templates.
    """
    tool_calls_hf = _normalize_tool_calls(tool_calls)
    tools = _build_tools_schema(tool_calls_hf)
    tool_results = _normalize_tool_results(tool_calls_hf, results)

    messages: List[Dict[str, Any]] = [
        {"role": "developer", "content": FUNCTIONGEMMA_DEVELOPER_MSG},
        {"role": "user", "content": prompt or ""},
    ]

    if tool_calls_hf:
        # Tool call turn (assistant with tool_calls field, content is null)
        messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls_hf})

    if tool_results:
        # Tool execution result turn (role tool, content in recommended shape)
        messages.append({"role": "tool", "content": tool_results})

    if include_final_assistant:
        messages.append({"role": "assistant", "content": final_assistant_text or ""})

    return messages, tools


# =============================================================================
# Dataset
# =============================================================================

class FunctionGemmaAIResponseDataset(Dataset):
    """
    Dataset for training FunctionGemma to generate final natural language responses.

    We build the *prompt* using tokenizer.apply_chat_template on:
      developer -> user -> (assistant tool_calls) -> (tool results)
    with add_generation_prompt=True.

    Then the *completion* is:
      ai_response + "<end_of_turn>"

    Labels are masked (-100) for all prompt tokens so loss is only on completion tokens.
    """

    def __init__(self, data: list, tokenizer, max_seq_len: int = MAX_SEQ_LENGTH):
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len

        self.data = [
            item for item in data
            if item.get("ai_response") and item["ai_response"].strip()
        ]
        print(f"Filtered to {len(self.data)} items with ai_response (from {len(data)} total)")

    def __len__(self):
        return len(self.data)

    def _format_prompt_and_completion(self, item: dict) -> Tuple[str, str]:
        prompt = item.get("prompt", "")
        tool_calls = item.get("tool_calls", [])
        results = item.get("responses", [])
        target = item["ai_response"].strip()

        # Build messages for prompt (no final assistant)
        messages, tools = _build_messages_for_example(
            prompt=prompt,
            tool_calls=tool_calls,
            results=results,
            include_final_assistant=False,
        )

        # This yields a string ending at the exact point where the model should start generating.
        # (FunctionGemma template handles tool declarations/calls/results tokens correctly.)
        prompt_text = self.tokenizer.apply_chat_template(
            messages,
            tools=tools,
            add_generation_prompt=True,
            tokenize=False,
        )

        # Completion: final answer + end_of_turn marker (as in template examples).
        completion_text = target + "<end_of_turn>"

        return prompt_text, completion_text

    def __getitem__(self, idx):
        item = self.data[idx]
        prompt_text, completion_text = self._format_prompt_and_completion(item)

        full_text = prompt_text + completion_text

        enc = self.tokenizer(
            full_text,
            max_length=self.max_seq_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        input_ids = enc["input_ids"].squeeze(0)
        attention_mask = enc["attention_mask"].squeeze(0)

        # Labels are next-token prediction; mask prompt portion.
        labels = input_ids.clone()

        # Compute prompt token length (without padding)
        prompt_enc = self.tokenizer(
            prompt_text,
            max_length=self.max_seq_len,
            padding=False,
            truncation=True,
            return_tensors="pt",
        )
        prompt_len = prompt_enc["input_ids"].shape[1]

        # Mask prompt tokens
        labels[:prompt_len] = -100

        # Mask padding tokens too
        pad_id = self.tokenizer.pad_token_id
        if pad_id is not None:
            labels[labels == pad_id] = -100

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }


# =============================================================================
# Training
# =============================================================================

def get_lr_multiplier(epoch: int, warmup_epochs: int, total_epochs: int) -> float:
    """Warmup + cosine decay learning rate schedule."""
    if epoch < warmup_epochs:
        return (epoch + 1) / warmup_epochs
    progress = (epoch - warmup_epochs) / max(1, (total_epochs - warmup_epochs))
    return 0.5 * (1 + math.cos(math.pi * progress))


def train():
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")

    print(f"\nLoading model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME,token=userdata.get("HF_TOKEN"))
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME,token=userdata.get("HF_TOKEN"))
    model.to(DEVICE)

    # Ensure pad token exists for batching
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("\nLoading training data...")
    all_data = load_all_training_data()

    dataset = FunctionGemmaAIResponseDataset(all_data, tokenizer)

    if len(dataset) == 0:
        print("ERROR: No training data with ai_response found!")
        return None, None

    if DRY_RUN:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - Showing sample formatted data")
        print("=" * 60)
        for i in range(min(3, len(dataset))):
            item = dataset.data[i]
            prompt_text, completion_text = dataset._format_prompt_and_completion(item)
            print(f"\n--- Sample {i+1} ---")
            print("PROMPT (what the model sees):")
            print(prompt_text)
            print("\nCOMPLETION (what the model should generate):")
            print(completion_text)
        print(f"\nTotal samples with ai_response: {len(dataset)}")
        return model, tokenizer

    # Train/val split
    val_size = max(1, int(len(dataset) * 0.1))
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(42)
    )
    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}")

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=WEIGHT_DECAY)
    scaler = torch.amp.GradScaler('cuda')

    best_val_loss = float("inf")
    patience_counter = 0

    print(f"\nStarting training for {EPOCHS} epochs...")
    print(f"  Warmup: {WARMUP_EPOCHS} epochs, LR: {BASE_LR}, Patience: {PATIENCE}")

    for epoch in range(EPOCHS):
        lr_mult = get_lr_multiplier(epoch, WARMUP_EPOCHS, EPOCHS)
        current_lr = BASE_LR * lr_mult
        for pg in optimizer.param_groups:
            pg["lr"] = current_lr

        # ==================== TRAIN ====================
        model.train()
        total_train_loss = 0.0

        for batch_idx, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(DEVICE)
            attention_mask = batch["attention_mask"].to(DEVICE)
            labels = batch["labels"].to(DEVICE)

            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast('cuda', dtype=torch.bfloat16):
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
                )
                loss = outputs.loss

            scaler.scale(loss).backward()

            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)

            scaler.step(optimizer)
            scaler.update()

            total_train_loss += loss.item()

            if (batch_idx + 1) % 50 == 0:
                avg_loss = total_train_loss / (batch_idx + 1)
                print(f"  Epoch {epoch+1}, Batch {batch_idx+1}/{len(train_loader)}, "
                      f"Loss: {avg_loss:.4f}, LR: {current_lr:.2e}")

        avg_train_loss = total_train_loss / max(1, len(train_loader))

        # ==================== VALIDATION ====================
        model.eval()
        total_val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(DEVICE)
                attention_mask = batch["attention_mask"].to(DEVICE)
                labels = batch["labels"].to(DEVICE)

                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
                )
                total_val_loss += outputs.loss.item()

        avg_val_loss = total_val_loss / max(1, len(val_loader))

        print(f"Epoch {epoch+1}/{EPOCHS} | Train: {avg_train_loss:.4f} | "
              f"Val: {avg_val_loss:.4f} | LR: {current_lr:.2e}")

        # Save best model + early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0

            save_path = Path(OUTPUT_DIR)
            save_path.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(save_path)
            tokenizer.save_pretrained(save_path)
            print(f"  ✓ New best! Saved to {save_path}")
        else:
            patience_counter += 1
            print(f"  No improvement ({patience_counter}/{PATIENCE})")
            if patience_counter >= PATIENCE:
                print(f"\nEarly stopping triggered after {epoch+1} epochs")
                break

    print("\n" + "=" * 60)
    print(f"Training complete! Best val loss: {best_val_loss:.4f}")
    print(f"Model saved to: {OUTPUT_DIR}")

    return model, tokenizer


# =============================================================================
# Demo / Inference
# =============================================================================

def generate_response(model, tokenizer, prompt: str, tool_calls: list, results: list) -> str:
    """
    Generate a final response given user prompt, tool calls, and tool results.

    We format with the official FunctionGemma template:
      developer -> user -> assistant(tool_calls) -> tool(results) -> (generate assistant)

    NOTE: This function generates the *final* answer, not the tool call.
    """
    model.eval()

    messages, tools = _build_messages_for_example(
        prompt=prompt,
        tool_calls=tool_calls,
        results=results,
        include_final_assistant=False,
    )

    prompt_text = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=True,
        tokenize=False,
    )

    print("\nFormatted prompt:\n" + prompt_text)

    inputs = tokenizer(
        prompt_text,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
    ).to(DEVICE)

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            num_beams=4,
            pad_token_id=tokenizer.eos_token_id,
        )

    gen = out[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(gen, skip_special_tokens=True)
    return text


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import sys

    DEMO_ONLY = "--demo" in sys.argv

    if DEMO_ONLY:
        print(f"Loading saved model from: {OUTPUT_DIR}")
        tokenizer = AutoTokenizer.from_pretrained(OUTPUT_DIR)
        model = AutoModelForCausalLM.from_pretrained(OUTPUT_DIR)
        model.to(DEVICE)

        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
    else:
        model, tokenizer = train()

    if model is not None and tokenizer is not None:
        print("\n" + "=" * 60)
        print("DEMO INFERENCE")
        print("=" * 60)

        response = generate_response(
            model, tokenizer,
            prompt="Do I have more than 5 hours of battery left?",
            tool_calls=["vitals_batt_time_left"],
            results=[{"intent": "vitals_batt_time_left", "return": 7.5}],
        )
        print(f"\nGenerated: {response}")
