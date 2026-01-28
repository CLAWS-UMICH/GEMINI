"""
AI Response Training Script for Flan-T5 (or other seq2seq models).

Trains a model to generate natural language responses given:
- User's original query
- Tool calls that were made
- Results from those tool calls

Uses the functiongemma-style format for input structuring.
"""

import json
import math
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader, random_split
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
)

# Import data loader from existing module
from simpledatacombine import load_all_training_data


# =============================================================================
# Configuration - Edit these to change behavior
# =============================================================================

MODEL_NAME = "HuggingFaceTB/SmolLM2-360M-Instruct"  # Try: google/flan-t5-base, google/flan-t5-large
OUTPUT_DIR = "ai_response_model"
MAX_INPUT_LENGTH = 512
MAX_TARGET_LENGTH = 128
BATCH_SIZE = 8

# Training settings (inspired by simpletrain)
EPOCHS = 30
BASE_LR = 2e-5
WEIGHT_DECAY = 0.01
WARMUP_EPOCHS = 2
MAX_GRAD_NORM = 1.0  # Gradient clipping
PATIENCE = 5  # Early stopping patience

# Set to True to just show sample data without training
DRY_RUN = False

# Device - just use cuda
DEVICE = torch.device("cuda")


# =============================================================================
# Dataset
# =============================================================================

class AIResponseDataset(Dataset):
    """
    Dataset for training AI response generation.
    
    Filters to only include datapoints that have a non-empty ai_response field.
    Formats input following the functiongemma template.
    """
    
    def __init__(self, data: list, tokenizer, max_input_len: int = MAX_INPUT_LENGTH, 
                 max_target_len: int = MAX_TARGET_LENGTH):
        self.tokenizer = tokenizer
        self.max_input_len = max_input_len
        self.max_target_len = max_target_len
        
        # Filter to only items with ai_response
        self.data = [
            item for item in data 
            if item.get("ai_response") and item["ai_response"].strip()
        ]
        
        print(f"Filtered to {len(self.data)} items with ai_response (from {len(data)} total)")
    
    def __len__(self):
        return len(self.data)
    
    def _format_input(self, item: dict) -> str:
        """
        Format input following the functiongemma template:
        
        User: <prompt>
        Function calls: [<tool1>, <tool2>, ...]
        Results: <JSON of responses>
        """
        prompt = item.get("prompt", "")
        tool_calls = item.get("tool_calls", [])
        responses = item.get("responses", [])
        
        # Format tool calls as list
        tools_str = ", ".join(tool_calls) if tool_calls else "none"
        
        # Format responses as compact JSON
        if responses:
            results_str = json.dumps(responses, separators=(",", ":"))
        else:
            results_str = "[]"
        
        input_text = f"User: {prompt}\nFunction calls: [{tools_str}]\nResults: {results_str}"
        return input_text
    
    def __getitem__(self, idx):
        item = self.data[idx]
        
        input_text = self._format_input(item)
        target_text = item["ai_response"]
        
        # Tokenize input
        input_encoding = self.tokenizer(
            input_text,
            max_length=self.max_input_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        
        # Tokenize target
        target_encoding = self.tokenizer(
            target_text,
            max_length=self.max_target_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        
        # Get labels (replace padding token id with -100 for loss calculation)
        labels = target_encoding["input_ids"].squeeze()
        labels[labels == self.tokenizer.pad_token_id] = -100
        
        return {
            "input_ids": input_encoding["input_ids"].squeeze(),
            "attention_mask": input_encoding["attention_mask"].squeeze(),
            "labels": labels,
        }


# =============================================================================
# Training
# =============================================================================

def get_lr_multiplier(epoch: int, warmup_epochs: int, total_epochs: int) -> float:
    """Warmup + cosine decay learning rate schedule."""
    if epoch < warmup_epochs:
        return (epoch + 1) / warmup_epochs
    else:
        progress = (epoch - warmup_epochs) / (total_epochs - warmup_epochs)
        return 0.5 * (1 + math.cos(math.pi * progress))


def train():
    """Main training function."""
    
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")
    
    # Load tokenizer and model
    print(f"\nLoading model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    model.to(DEVICE)
    
    # Load data
    print("\nLoading training data...")
    all_data = load_all_training_data()
    
    # Create dataset
    dataset = AIResponseDataset(all_data, tokenizer)
    
    if len(dataset) == 0:
        print("ERROR: No training data with ai_response found!")
        return None, None
    
    # Dry run mode - just show samples
    if DRY_RUN:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - Showing sample data")
        print("=" * 60)
        
        for i in range(min(3, len(dataset))):
            item = dataset.data[i]
            input_text = dataset._format_input(item)
            print(f"\n--- Sample {i+1} ---")
            print(f"INPUT:\n{input_text}")
            print(f"\nTARGET:\n{item['ai_response']}")
        
        print(f"\n\nTotal samples with ai_response: {len(dataset)}")
        return model, tokenizer
    
    # Train/val split
    val_size = max(1, int(len(dataset) * 0.1))
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(42)
    )
    
    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}")
    
    # DataLoaders
    train_loader = DataLoader(
        train_dataset, 
        batch_size=BATCH_SIZE, 
        shuffle=True,
        num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, 
        batch_size=BATCH_SIZE, 
        shuffle=False,
        num_workers=0
    )
    
    # AdamW optimizer with weight decay
    optimizer = torch.optim.AdamW(model.parameters(), lr=BASE_LR, weight_decay=WEIGHT_DECAY)
    
    # Mixed precision - use bfloat16 which is more stable than fp16
    scaler = torch.amp.GradScaler('cuda')
    
    # Training state
    best_val_loss = float("inf")
    patience_counter = 0
    
    print(f"\nStarting training for {EPOCHS} epochs...")
    print(f"  Warmup: {WARMUP_EPOCHS} epochs, LR: {BASE_LR}, Patience: {PATIENCE}")
    
    for epoch in range(EPOCHS):
        # Adjust learning rate with warmup + cosine decay
        lr_mult = get_lr_multiplier(epoch, WARMUP_EPOCHS, EPOCHS)
        current_lr = BASE_LR * lr_mult
        for param_group in optimizer.param_groups:
            param_group['lr'] = current_lr
        
        # ==================== TRAIN ====================
        model.train()
        total_train_loss = 0
        
        for batch_idx, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(DEVICE)
            attention_mask = batch["attention_mask"].to(DEVICE)
            labels = batch["labels"].to(DEVICE)
            
            optimizer.zero_grad()
            
            # Forward pass with mixed precision (bfloat16 is more stable)
            with torch.amp.autocast('cuda', dtype=torch.bfloat16):
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels
                )
                loss = outputs.loss
            
            scaler.scale(loss).backward()
            
            # Gradient clipping for stability
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
            
            scaler.step(optimizer)
            scaler.update()
            
            total_train_loss += loss.item()
            
            if (batch_idx + 1) % 50 == 0:
                avg_loss = total_train_loss / (batch_idx + 1)
                print(f"  Epoch {epoch+1}, Batch {batch_idx+1}/{len(train_loader)}, Loss: {avg_loss:.4f}, LR: {current_lr:.2e}")
        
        avg_train_loss = total_train_loss / len(train_loader)
        
        # ==================== VALIDATION ====================
        model.eval()
        total_val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(DEVICE)
                attention_mask = batch["attention_mask"].to(DEVICE)
                labels = batch["labels"].to(DEVICE)
                
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels
                )
                total_val_loss += outputs.loss.item()
        
        avg_val_loss = total_val_loss / len(val_loader)
        
        # Log epoch stats
        print(f"Epoch {epoch+1}/{EPOCHS} | Train: {avg_train_loss:.4f} | Val: {avg_val_loss:.4f} | LR: {current_lr:.2e}")
        
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
    """Generate a response given user prompt, tool calls, and results."""
    
    model.eval()
    
    # Build input
    tools_str = ", ".join(tool_calls) if tool_calls else "none"
    results_str = json.dumps(results, separators=(",", ":")) if results else "[]"
    input_text = f"User: {prompt}\nFunction calls: [{tools_str}]\nResults: {results_str}"
    
    print(f"\nInput:\n{input_text}")
    
    # Tokenize
    inputs = tokenizer(
        input_text,
        max_length=MAX_INPUT_LENGTH,
        truncation=True,
        return_tensors="pt"
    ).to(DEVICE)
    
    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_length=MAX_TARGET_LENGTH,
            num_beams=4,
            early_stopping=True
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return response


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Check for --demo flag to skip training
    DEMO_ONLY = "--demo" in sys.argv
    
    if DEMO_ONLY:
        # Load saved model instead of training
        print(f"Loading saved model from: {OUTPUT_DIR}")
        tokenizer = AutoTokenizer.from_pretrained(OUTPUT_DIR)
        model = AutoModelForSeq2SeqLM.from_pretrained(OUTPUT_DIR)
        model.to(DEVICE)
    else:
        # Train the model
        model, tokenizer = train()
    
    # If we have a model (either from training or dry-run), run demo inference
    if model is not None and tokenizer is not None:
        print("\n" + "=" * 60)
        print("DEMO INFERENCE")
        print("=" * 60)
        
        # Demo 1: Battery check
        response = generate_response(
            model, tokenizer,
            prompt="Do I have less than 5 hours of battery left?",
            tool_calls=["vitals_batt_time_left"],
            results=[{"intent": "vitals_batt_time_left", "return": 7.5}]
        )
        print(f"\nGenerated: {response}")

        # Demo 2: Multi-intent test - heart rate + add task (tests generalization)
        response = generate_response(
            model, tokenizer,
            prompt="What's my heart rate and add a task to check the oxygen tank",
            tool_calls=["vitals_heart_rate", "Add_task"],
            results=[
                {"intent": "vitals_heart_rate", "return": 82},
                {"intent": "Add_task", "return": True}
            ]
        )
        print(f"\nGenerated (multi-intent): {response}")

        # Demo 3: Another multi-intent - warnings + navigation  
        response = generate_response(
            model, tokenizer,
            prompt="Are there any warnings and reroute me around the crater",
            tool_calls=["get_warnings", "reroute_navigation"],
            results=[
                {"intent": "get_warnings", "return": []},
                {"intent": "reroute_navigation", "return": True}
            ]
        )
        print(f"\nGenerated (warnings + reroute): {response}")
