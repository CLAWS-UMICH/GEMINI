"""
AI Response Training Script with LoRA for FunctionGemma.

Trains a LoRA adapter to generate natural language responses given:
- User's original query
- Tool calls that were made
- Results from those tool calls

Uses FunctionGemma's chat template for exact tool-call/tool-response formatting.
"""

import json
import math
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader, random_split
from transformers import AutoProcessor, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType, PeftModel
# Import data loader from existing module
from simpledatacombine import load_all_training_data


# =============================================================================
# Configuration - Edit these to change behavior
# =============================================================================
import os
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError("HF_TOKEN not set. Export it before running.")

MODEL_NAME = "google/functiongemma-270m-it"  # Base model (FunctionGemma)
OUTPUT_DIR = "ai_response_lora"  # LoRA adapter output
MAX_LENGTH = 512
BATCH_SIZE = 8  # Per-step batch size

# LoRA settings - smaller to prevent overfitting
LORA_R = 4            # Rank of the low-rank matrices (was 16)
LORA_ALPHA = 8        # Scaling factor (was 32)
LORA_DROPOUT = 0.2   # Dropout for LoRA layers (was 0.05)
LORA_TARGET_MODULES = ["q_proj", "v_proj"]  # Fewer layers to adapt (was q,v,k,o)

# Training settings
EPOCHS = 300
BASE_LR = 5e-5  # Higher LR works well with LoRA
WEIGHT_DECAY = 0.05
WARMUP_EPOCHS = 2
MAX_GRAD_NORM = 1.0
PATIENCE = 10

# Set to True to just show sample data without training
DRY_RUN = False

# Device + dtype selection
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if DEVICE.type == "cuda":
    if torch.cuda.is_bf16_supported():
        MODEL_DTYPE = torch.bfloat16
    else:
        MODEL_DTYPE = torch.float16
    # Faster matmul on Ampere+ without extra memory
    torch.backends.cuda.matmul.allow_tf32 = True
else:
    MODEL_DTYPE = torch.float32

# FunctionGemma requires a developer prompt for tool use
SYSTEM_PROMPT = (
    "You are an EVA assistant. Use tool outputs to answer the user's request. "
    "Respond in a concise, natural sentence."
)

# Paths
SCRIPT_DIR = Path(__file__).parent
NAMES_FILE = SCRIPT_DIR / "data" / "names.json"
TOOLS_CACHE = None
TOOLS_MAP_CACHE = None


# =============================================================================
# Tool schema helpers (FunctionGemma tools format)
# =============================================================================

def load_intents_file(filepath: Path) -> list:
    """Load names.json and return the list of intent definitions."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def build_tool_schemas(intents: list) -> list:
    """
    Build FunctionGemma tool schemas from names.json.

    We keep parameters optional so empty args remain valid for this dataset.
    """
    tools = []
    for intent in intents:
        tokens = set(intent.get("tokens", []))
        properties = {}

        if "TASK_NAME" in tokens:
            properties["task"] = {"type": "string", "description": "Task name or title."}
        if "WAYPOINT_NAME" in tokens:
            properties["waypoint"] = {"type": "string", "description": "Waypoint name."}
        if "NAVIGATION_TARGET_NAME" in tokens:
            properties["destination"] = {"type": "string", "description": "Navigation target."}
        if "COORDINATE_TARGET_NAME" in tokens:
            properties["target"] = {"type": "string", "description": "Coordinate target."}

        tool = {
            "type": "function",
            "function": {
                "name": intent["name"],
                "description": intent["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [],
                },
            },
        }
        tools.append(tool)

    return tools


def build_tool_map(tools: list) -> dict:
    """Build a name -> tool schema map."""
    return {tool["function"]["name"]: tool for tool in tools}


def get_tools() -> list:
    """Load and cache tool schemas."""
    global TOOLS_CACHE, TOOLS_MAP_CACHE
    if TOOLS_CACHE is None:
        intents = load_intents_file(NAMES_FILE)
        TOOLS_CACHE = build_tool_schemas(intents)
        TOOLS_MAP_CACHE = build_tool_map(TOOLS_CACHE)
    return TOOLS_CACHE


def get_tools_map() -> dict:
    """Load and cache tool schema map."""
    global TOOLS_CACHE, TOOLS_MAP_CACHE
    if TOOLS_MAP_CACHE is None:
        intents = load_intents_file(NAMES_FILE)
        TOOLS_CACHE = build_tool_schemas(intents)
        TOOLS_MAP_CACHE = build_tool_map(TOOLS_CACHE)
    return TOOLS_MAP_CACHE


def build_messages(
    prompt: str,
    tool_calls: list,
    responses: list,
    ai_response: str | None,
) -> list:
    """
    Build a FunctionGemma-compatible message list.

    Tool responses must be passed as role="tool" with content containing
    {name, response} or a list of those objects.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    if tool_calls:
        calls_payload = [
            {"type": "function", "function": {"name": name, "arguments": json.dumps({})}}
            for name in tool_calls
        ]
        messages.append({"role": "assistant", "tool_calls": calls_payload})

    if responses:
        for r in responses:
            tool_name = r.get("intent", "")
            tool_content = json.dumps(r.get("return"))
            messages.append({"role": "tool", "name": tool_name, "content": tool_content})

    if ai_response is not None:
        messages.append({"role": "assistant", "content": ai_response})

    return messages


# =============================================================================
# Dataset for Causal LM
# =============================================================================

class AIResponseDataset(Dataset):
    """
    Dataset for training AI response generation with FunctionGemma.

    For causal LMs, we concatenate input + output and mask the input portion
    in labels so the model only learns to predict the response.
    """

    def __init__(self, data: list, processor, tools: list, tool_map: dict, max_length: int = MAX_LENGTH):
        self.processor = processor
        self.tokenizer = getattr(processor, "tokenizer", processor)
        self.tools = tools
        self.tool_map = tool_map
        self.max_length = max_length

        # Ensure pad token exists
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Filter to only items with ai_response
        self.data = [
            item for item in data
            if item.get("ai_response") and item["ai_response"].strip()
        ]
        self.reset_truncation_stats()

        print(f"Filtered to {len(self.data)} items with ai_response (from {len(data)} total)")

    def __len__(self):
        return len(self.data)

    def reset_truncation_stats(self):
        self.truncation_count = 0
        self.truncation_total_overflow = 0
        self.truncation_max_overflow = 0

    def get_truncation_stats(self):
        if self.truncation_count == 0:
            avg_overflow = 0
        else:
            avg_overflow = self.truncation_total_overflow / self.truncation_count
        return {
            "count": self.truncation_count,
            "avg_overflow": avg_overflow,
            "max_overflow": self.truncation_max_overflow,
        }

    def __getitem__(self, idx):
        item = self.data[idx]

        prompt = item.get("prompt", "")
        tool_calls = item.get("tool_calls", [])
        responses = item.get("responses", [])
        response_text = item["ai_response"].strip()

        # Build messages for prefix (no final assistant response)
        prefix_messages = build_messages(
            prompt=prompt,
            tool_calls=tool_calls,
            responses=responses,
            ai_response=None,
        )
        tools_subset = None
        if tool_calls:
            tools_subset = [self.tool_map[name] for name in tool_calls if name in self.tool_map]

        prefix_text = self.processor.apply_chat_template(
            prefix_messages,
            tools=tools_subset,
            add_generation_prompt=True,
            tokenize=False,
        )

        # Build messages with the target response
        full_messages = build_messages(
            prompt=prompt,
            tool_calls=tool_calls,
            responses=responses,
            ai_response=response_text,
        )
        full_text = self.processor.apply_chat_template(
            full_messages,
            tools=tools_subset,
            add_generation_prompt=False,
            tokenize=False,
        )

        # Tokenize without truncation so we can left-truncate to keep the response
        prefix_ids = self.tokenizer(prefix_text, add_special_tokens=False)["input_ids"]
        full_ids = self.tokenizer(full_text, add_special_tokens=False)["input_ids"]

        if not full_ids:
            # Safety fallback to avoid empty sequences
            full_ids = [self.tokenizer.eos_token_id]

        orig_full_len = len(full_ids)
        overflow = max(0, orig_full_len - self.max_length)
        if overflow > 0:
            # Left-truncate to keep the end of the sequence (assistant response)
            full_ids = full_ids[overflow:]
            self.truncation_count += 1
            self.truncation_total_overflow += overflow
            if overflow > self.truncation_max_overflow:
                self.truncation_max_overflow = overflow

        prefix_len = max(0, len(prefix_ids) - overflow)
        if prefix_len >= len(full_ids):
            # Ensure at least one response token remains for loss
            prefix_len = max(0, len(full_ids) - 1)

        pad_len = self.max_length - len(full_ids)
        if pad_len < 0:
            pad_len = 0

        pad_id = self.tokenizer.pad_token_id
        input_ids = torch.tensor(full_ids + [pad_id] * pad_len, dtype=torch.long)
        attention_mask = torch.tensor([1] * len(full_ids) + [0] * pad_len, dtype=torch.long)

        labels = input_ids.clone()
        labels[:prefix_len] = -100  # Mask prefix
        if pad_len > 0:
            labels[-pad_len:] = -100  # Mask padding

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
    
    # Load processor/tokenizer and base model
    print(f"\nLoading base model: {MODEL_NAME}")
    processor = AutoProcessor.from_pretrained(MODEL_NAME, token=HF_TOKEN)
    tokenizer = getattr(processor, "tokenizer", processor)
    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=MODEL_DTYPE,
        token=HF_TOKEN,
    )
    
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
    
    # Load tool schemas
    print("\nLoading tool schemas...")
    intents = load_intents_file(NAMES_FILE)
    tools = build_tool_schemas(intents)
    tools_map = build_tool_map(tools)

    # Load data
    print("\nLoading training data...")
    all_data = load_all_training_data()
    
    # Create dataset
    dataset = AIResponseDataset(all_data, processor, tools, tools_map)
    
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
            tools_subset = None
            if item.get("tool_calls"):
                tools_subset = [tools_map[name] for name in item["tool_calls"] if name in tools_map]
            prompt_text = processor.apply_chat_template(
                build_messages(
                    prompt=item.get("prompt", ""),
                    tool_calls=item.get("tool_calls", []),
                    responses=item.get("responses", []),
                    ai_response=None,
                ),
                tools=tools_subset,
                add_generation_prompt=True,
                tokenize=False,
            )
            print(f"\n--- Sample {i+1} ---")
            print(f"PROMPT:\n{prompt_text}")
            print(f"\nRESPONSE:\n{item['ai_response']}")
        
        print(f"\n\nTotal samples with ai_response: {len(dataset)}")
        return model, processor
    
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
    print(f"  Warmup: {WARMUP_EPOCHS} epochs, LR: {BASE_LR}, Patience: {PATIENCE}, Batch: {BATCH_SIZE}")
    
    for epoch in range(EPOCHS):
        dataset.reset_truncation_stats()
        total_samples = len(train_dataset) + len(val_dataset)
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

            if DEVICE.type == "cuda":
                with torch.amp.autocast(device_type="cuda", dtype=MODEL_DTYPE):
                    outputs = model(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        labels=labels,
                    )
                    loss = outputs.loss
            else:
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
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

        trunc_stats = dataset.get_truncation_stats()
        if trunc_stats["count"] > 0:
            pct = (trunc_stats["count"] / max(1, total_samples)) * 100
            print(
                f"  Truncation: {trunc_stats['count']}/{total_samples} "
                f"({pct:.2f}%) | avg overflow: {trunc_stats['avg_overflow']:.1f} "
                f"| max overflow: {trunc_stats['max_overflow']}"
            )
        
        # Save best LoRA adapter + early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            save_path = Path(OUTPUT_DIR)
            save_path.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(save_path)  # Saves only LoRA weights
            processor.save_pretrained(save_path)
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
    
    return model, processor


# =============================================================================
# Demo / Inference
# =============================================================================

def generate_response(model, processor, prompt: str, tool_calls: list, results: list) -> str:
    """Generate a response given user prompt, tool calls, and results."""
    
    model.eval()

    tools_map = get_tools_map()
    messages = build_messages(
        prompt=prompt,
        tool_calls=tool_calls,
        responses=results,
        ai_response=None,
    )

    tools_subset = None
    if tool_calls:
        tools_subset = [tools_map[name] for name in tool_calls if name in tools_map]

    input_text = processor.apply_chat_template(
        messages,
        tools=tools_subset,
        add_generation_prompt=True,
        tokenize=False,
    )

    print(f"\nInput:\n{input_text}")

    tokenizer = getattr(processor, "tokenizer", processor)
    inputs = tokenizer(input_text, return_tensors="pt").to(DEVICE)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return response.strip()


def load_lora_model():
    """Load base model with LoRA adapter for inference."""
    print(f"Loading base model: {MODEL_NAME}")
    processor_source = OUTPUT_DIR if Path(OUTPUT_DIR).exists() else MODEL_NAME
    processor = AutoProcessor.from_pretrained(processor_source)
    tokenizer = getattr(processor, "tokenizer", processor)
    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=MODEL_DTYPE)
    
    print(f"Loading LoRA adapter from: {OUTPUT_DIR}")
    model = PeftModel.from_pretrained(base_model, OUTPUT_DIR)
    model.to(DEVICE)
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    return model, processor


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
        model, processor = load_lora_model()
    else:
        # Train the LoRA adapter
        model, processor = train()
    
    # If we have a model, run demo inference
    if model is not None and processor is not None:
        print("\n" + "=" * 60)
        print("DEMO INFERENCE")
        print("=" * 60)
        
        # Demo 1: Battery check
        response = generate_response(
            model, processor,
            prompt="Do I have less than 5 hours of battery left?",
            tool_calls=["vitals_batt_time_left"],
            results=[{"intent": "vitals_batt_time_left", "return": 7.5}]
        )
        print(f"\nGenerated: {response}")

        # Demo 2: Multi-intent test - heart rate + add task (tests generalization)
        response = generate_response(
            model, processor,
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
            model, processor,
            prompt="Are there any warnings and reroute me around the crater",
            tool_calls=["get_warnings", "reroute_navigation"],
            results=[
                {"intent": "get_warnings", "return": []},
                {"intent": "reroute_navigation", "return": True}
            ]
        )
        print(f"\nGenerated (warnings + reroute): {response}")
