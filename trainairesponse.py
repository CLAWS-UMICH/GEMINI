"""
AI Response Training Script with LoRA for Causal LMs (SmolLM2, etc).

Trains a LoRA adapter to generate natural language responses given:
- User's original query
- Tool calls that were made
- Results from those tool calls

Uses PEFT LoRA for efficient fine-tuning.
"""

import json
import math
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader, random_split
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType, PeftModel

# Import data loader from existing module
from simpledatacombine import load_all_training_data


# =============================================================================
# Configuration - Edit these to change behavior
# =============================================================================

MODEL_NAME = "HuggingFaceTB/SmolLM2-360M-Instruct"  # Base model
OUTPUT_DIR = "ai_response_lora"  # LoRA adapter output
MAX_LENGTH = 512
BATCH_SIZE = 8  # Can use larger batch with LoRA (fewer trainable params)

# LoRA settings - smaller to prevent overfitting
LORA_R = 4            # Rank of the low-rank matrices (was 16)
LORA_ALPHA = 8        # Scaling factor (was 32)
LORA_DROPOUT = 0.15   # Dropout for LoRA layers (was 0.05)
LORA_TARGET_MODULES = ["q_proj", "v_proj"]  # Fewer layers to adapt (was q,v,k,o)

# Training settings
EPOCHS = 30
BASE_LR = 1e-4  # Higher LR works well with LoRA
WEIGHT_DECAY = 0.01
WARMUP_EPOCHS = 2
MAX_GRAD_NORM = 1.0
PATIENCE = 5

# Set to True to just show sample data without training
DRY_RUN = False

# Device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# =============================================================================
# Dataset for Causal LM
# =============================================================================

class AIResponseDataset(Dataset):
    """
    Dataset for training AI response generation with Causal LMs.
    
    For causal LMs, we concatenate input + output and mask the input portion
    in labels so the model only learns to predict the response.
    """
    
    def __init__(self, data: list, tokenizer, max_length: int = MAX_LENGTH):
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        # Ensure pad token exists
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        # Filter to only items with ai_response
        self.data = [
            item for item in data 
            if item.get("ai_response") and item["ai_response"].strip()
        ]
        
        print(f"Filtered to {len(self.data)} items with ai_response (from {len(data)} total)")
    
    def __len__(self):
        return len(self.data)
    
    def _format_prompt(self, item: dict) -> str:
        """Format input as a chat-style prompt."""
        prompt = item.get("prompt", "")
        tool_calls = item.get("tool_calls", [])
        responses = item.get("responses", [])
        
        tools_str = ", ".join(tool_calls) if tool_calls else "none"
        results_str = json.dumps(responses, separators=(",", ":")) if responses else "[]"
        
        # Format as instruction for the model
        system_context = f"User query: {prompt}\nFunction calls: [{tools_str}]\nResults: {results_str}\nGenerate a natural response:"
        return system_context
    
    def __getitem__(self, idx):
        item = self.data[idx]
        
        prompt = self._format_prompt(item)
        response = item["ai_response"]
        
        # Full text: prompt + response
        full_text = f"{prompt} {response}{self.tokenizer.eos_token}"
        
        # Tokenize the full sequence
        full_encoding = self.tokenizer(
            full_text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        
        # Tokenize just the prompt to know where to start labels
        prompt_encoding = self.tokenizer(
            prompt + " ",  # Include the space separator
            max_length=self.max_length,
            truncation=True,
            return_tensors="pt"
        )
        prompt_len = prompt_encoding["input_ids"].shape[1]
        
        input_ids = full_encoding["input_ids"].squeeze()
        attention_mask = full_encoding["attention_mask"].squeeze()
        
        # Labels: -100 for prompt tokens (don't compute loss), actual ids for response
        labels = input_ids.clone()
        labels[:prompt_len] = -100  # Mask prompt
        labels[labels == self.tokenizer.pad_token_id] = -100  # Mask padding
        
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
    else:
        progress = (epoch - warmup_epochs) / (total_epochs - warmup_epochs)
        return 0.5 * (1 + math.cos(math.pi * progress))


def train():
    """Main training function with LoRA."""
    
    print(f"Using device: {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    # Load tokenizer and base model
    print(f"\nLoading base model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.bfloat16)
    
    # Ensure pad token
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        base_model.config.pad_token_id = tokenizer.pad_token_id
    
    # Configure LoRA
    print(f"\nConfiguring LoRA (r={LORA_R}, alpha={LORA_ALPHA})")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
    )
    
    # Wrap model with LoRA
    model = get_peft_model(base_model, lora_config)
    model.to(DEVICE)
    
    # Print trainable parameters
    model.print_trainable_parameters()
    
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
            prompt = dataset._format_prompt(item)
            print(f"\n--- Sample {i+1} ---")
            print(f"PROMPT:\n{prompt}")
            print(f"\nRESPONSE:\n{item['ai_response']}")
        
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
    
    # AdamW optimizer - only LoRA params are trained
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()), 
        lr=BASE_LR, 
        weight_decay=WEIGHT_DECAY
    )
    
    # Training state
    best_val_loss = float("inf")
    patience_counter = 0
    
    print(f"\nStarting LoRA training for {EPOCHS} epochs...")
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
            
            # Forward pass with bfloat16
            with torch.amp.autocast('cuda', dtype=torch.bfloat16):
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels
                )
                loss = outputs.loss
            
            loss.backward()
            
            # Gradient clipping for stability
            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
            
            optimizer.step()
            
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
        
        # Save best LoRA adapter + early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            save_path = Path(OUTPUT_DIR)
            save_path.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(save_path)  # Saves only LoRA weights
            tokenizer.save_pretrained(save_path)
            print(f"  ✓ New best! LoRA adapter saved to {save_path}")
        else:
            patience_counter += 1
            print(f"  No improvement ({patience_counter}/{PATIENCE})")
            if patience_counter >= PATIENCE:
                print(f"\nEarly stopping triggered after {epoch+1} epochs")
                break
    
    print("\n" + "=" * 60)
    print(f"Training complete! Best val loss: {best_val_loss:.4f}")
    print(f"LoRA adapter saved to: {OUTPUT_DIR}")
    
    return model, tokenizer


# =============================================================================
# Demo / Inference
# =============================================================================

def generate_response(model, tokenizer, prompt: str, tool_calls: list, results: list) -> str:
    """Generate a response given user prompt, tool calls, and results."""
    
    model.eval()
    
    # Build input prompt
    tools_str = ", ".join(tool_calls) if tool_calls else "none"
    results_str = json.dumps(results, separators=(",", ":")) if results else "[]"
    input_text = f"User query: {prompt}\nFunction calls: [{tools_str}]\nResults: {results_str}\nGenerate a natural response:"
    
    print(f"\nInput:\n{input_text}")
    
    # Tokenize
    inputs = tokenizer(
        input_text,
        return_tensors="pt"
    ).to(DEVICE)
    
    # Generate (causal LM continues from input)
    with torch.no_grad():
        # outputs = model.generate(
        #     **inputs,
        #     max_new_tokens=100,
        #     do_sample=True,
        #     temperature=0.7,
        #     top_p=0.9,
        #     pad_token_id=tokenizer.pad_token_id,
        #     eos_token_id=tokenizer.eos_token_id
        # )
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
    
    # Decode only the new tokens (skip input)
    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return response.strip()


def load_lora_model():
    """Load base model with LoRA adapter for inference."""
    print(f"Loading base model: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.bfloat16)
    
    print(f"Loading LoRA adapter from: {OUTPUT_DIR}")
    model = PeftModel.from_pretrained(base_model, OUTPUT_DIR)
    model.to(DEVICE)
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    return model, tokenizer


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Check for flags
    DRY_RUN = "--dry-run" in sys.argv
    DEMO_ONLY = "--demo" in sys.argv
    
    if DEMO_ONLY:
        # Load base model + LoRA adapter
        model, tokenizer = load_lora_model()
    else:
        # Train the LoRA adapter
        model, tokenizer = train()
    
    # If we have a model, run demo inference
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
