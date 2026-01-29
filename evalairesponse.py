"""
Evaluation script for FunctionGemma LoRA Adapter.
Loads the trained LoRA model and runs a set of validation questions (unseen in training)
to verify generalization and response quality.
"""

import json
import torch
from pathlib import Path
from transformers import AutoProcessor, AutoModelForCausalLM
from peft import PeftModel
from dotenv import load_dotenv
import os

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================
HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_NAME = "google/functiongemma-270m-it"
LORA_PATH = "ai_response_lora"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SCRIPT_DIR = Path(__file__).parent
NAMES_FILE = SCRIPT_DIR / "data" / "names.json"

# =============================================================================
# Validation Data - Questions NOT in the training set
# =============================================================================
VALIDATION_CASES = [
    # 1. Vitals - Battery (Interpretive - "No" bias)
    {
        "category": "Vitals - Battery",
        "prompt": "Is the battery going to die soon?",
        "tool_calls": ["vitals_batt_time_left"],
        "results": [{"intent": "vitals_batt_time_left", "return": 8.2}],
        "expected_gist": "No, 8.2 hours remaining."
    },
    # 2. Vitals - Heart Rate (Interpretive - "No" bias)
    {
        "category": "Vitals - Heart Rate",
        "prompt": "Is my heart rate dangerously high?",
        "tool_calls": ["vitals_heart_rate"],
        "results": [{"intent": "vitals_heart_rate", "return": 65}],
        "expected_gist": "No, it is normal (65 bpm)."
    },
    # 3. Vitals - Oxygen Pressure (Interpretive - "No" bias)
    {
        "category": "Vitals - O2 Pressure",
        "prompt": "Do I have a leak in the primary oxygen tank?",
        "tool_calls": ["vitals_oxy_pri_pressure"],
        "results": [{"intent": "vitals_oxy_pri_pressure", "return": 2500.0}],
        "expected_gist": "No, pressure is stable/nominal (2500 psi)."
    },
    # 4. Vitals - O2 Pressure (Interpretive - True condition)
    {
        "category": "Vitals - O2 Pressure",
        "prompt": "Is primary oxygen critical?",
        "tool_calls": ["vitals_oxy_pri_pressure"],
        "results": [{"intent": "vitals_oxy_pri_pressure", "return": 150.0}],
        "expected_gist": "Yes, it is very low (150 psi)."
    },
     # 5. CO2 Production (Interpretive)
    {
        "category": "Vitals - CO2",
        "prompt": "Is my metabolic rate abnormal?",
        "tool_calls": ["vitals_co2_production"],
        "results": [{"intent": "vitals_co2_production", "return": 0.12}], 
        "expected_gist": "No, production is normal."
    },
    # 6. Task Management (Confirmation)
    {
        "category": "Tasks - Create",
        "prompt": "Did you successfully log the inspection task?",
        "tool_calls": ["Add_task"],
        "results": [{"intent": "Add_task", "return": True}],
        "expected_gist": "Yes, task added."
    },
    # 7. Navigation (Spatial Reasoning)
    {
        "category": "Navigation",
        "prompt": "Am I currently at the base?",
        "tool_calls": ["Get_coordinates"],
        "results": [{"intent": "Get_coordinates", "return": {"x": 500, "y": 1200, "z": 10}}],
        "expected_gist": "No, current coordinates are [500, 1200]."
    },
    # 8. Warnings (Interpretive)
    {
        "category": "Warnings",
        "prompt": "Is the EVA suit functioning perfectly?",
        "tool_calls": ["get_warnings"],
        "results": [{"intent": "get_warnings", "return": []}],
        "expected_gist": "Yes, no warnings found."
    },
    # 9. Comparison (O2 Storage - Reasoning)
    {
        "category": "Comparison - O2",
        "prompt": "Should I switch to the secondary tank?",
        "tool_calls": ["vitals_oxy_pri_storage", "vitals_oxy_sec_storage"],
        "results": [
            {"intent": "vitals_oxy_pri_storage", "return": 85},
            {"intent": "vitals_oxy_sec_storage", "return": 95}
        ],
        "expected_gist": "No, primary is still high (85%)."
    }
]

# =============================================================================
# Helper Functions (Adapted from trainairesponse.py)
# =============================================================================

def load_intents_file(filepath: Path) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def build_tool_schemas(intents: list) -> list:
    tools = []
    for intent in intents:
        tokens = set(intent.get("tokens", []))
        properties = {}
        if "TASK_NAME" in tokens:
            properties["task"] = {"type": "string", "description": "Task name."}
        if "WAYPOINT_NAME" in tokens:
            properties["waypoint"] = {"type": "string", "description": "Waypoint name."}
        
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
    return {tool["function"]["name"]: tool for tool in tools}

def build_messages(prompt: str, tool_calls: list, responses: list, ai_response: str | None = None) -> list:
    system_prompt = "You are an EVA assistant. Use tool outputs to answer the user's request. Respond in a concise, natural sentence."
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    if tool_calls:
        # Manually build function call content since chat template doesn't add <end_of_turn>
        # Format: <start_function_call>call:name{args}<end_function_call>
        call_parts = []
        for name in tool_calls:
            call_parts.append(f"<start_function_call>call:{name}{{}}<end_function_call>")
        # Add the calls as assistant content (chat template will wrap with turn markers)
        messages.append({"role": "assistant", "content": "".join(call_parts)})

    if responses:
        # FunctionGemma expects tool responses in a "developer" turn, not "tool" role
        # Format: <start_function_response>response:name{value:<escape>...<escape>}<end_function_response>
        response_parts = []
        for r in responses:
            tool_name = r.get("intent", "")
            tool_value = json.dumps(r.get("return"))
            # Build the function response format that FunctionGemma expects
            response_parts.append(f"<start_function_response>response:{tool_name}{{value:<escape>{tool_value}<escape>}}<end_function_response>")
        messages.append({"role": "developer", "content": "".join(response_parts)})
    
    if ai_response is not None:
        messages.append({"role": "assistant", "content": ai_response})

    return messages

def generate_response(model, processor, prompt: str, tool_calls: list, results: list, tools_map: dict) -> str:
    model.eval()
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
    
    # DEBUG: Print the formatted input for the first case to see what's wrong
    if "Is the battery going to die soon?" in prompt:
         print(f"\n[DEBUG] Input Text:\n{input_text}\n[DEBUG] End Input Text")
         if tools_subset:
             print(f"[DEBUG] Tools Subset count: {len(tools_subset)}")
         else:
             print("[DEBUG] Tools Subset is EMPTY/None")

    tokenizer = getattr(processor, "tokenizer", processor)
    
    # Ensure pad token exists
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    inputs = tokenizer(input_text, return_tensors="pt").to(DEVICE)
    
    # FunctionGemma stop tokens - <start_function_response> prevents hallucinated results
    stop_token_ids = [
        tokenizer.eos_token_id,
        tokenizer.convert_tokens_to_ids("<end_of_turn>"),
        tokenizer.convert_tokens_to_ids("<start_function_response>"),
    ]
    # Filter out any None/unknown tokens
    stop_token_ids = [t for t in stop_token_ids if t is not None and t != tokenizer.unk_token_id]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=stop_token_ids,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return response.strip()

# =============================================================================
# Main Evaluation Loop
# =============================================================================

def main():
    print(f"\n--- Starting Evaluation on {DEVICE} ---")
    
    # 1. Load Tools
    print("Loading tool schemas...")
    if not NAMES_FILE.exists():
        print(f"Error: {NAMES_FILE} not found.")
        return
        
    intents = load_intents_file(NAMES_FILE)
    tools = build_tool_schemas(intents)
    tools_map = build_tool_map(tools)
    
    # 2. Load Model + LoRA
    print(f"Loading Base Model: {MODEL_NAME}")
    
    # Prefer loading processor from LoRA adapter if it exists (contains correct chat template/config)
    processor_source = LORA_PATH if os.path.exists(LORA_PATH) else MODEL_NAME
    print(f"Loading processor from: {processor_source}")
    processor = AutoProcessor.from_pretrained(processor_source, token=HF_TOKEN)
    
    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, 
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32, 
        token=HF_TOKEN
    )
    
    print(f"Loading LoRA Adapter: {LORA_PATH}")
    if not os.path.exists(LORA_PATH):
        print(f"Error: LoRA path '{LORA_PATH}' does not exist. Train the model first!")
        return
        
    model = PeftModel.from_pretrained(base_model, LORA_PATH)
    model.to(DEVICE)
    
    # 3. Run Validation Cases
    print(f"\nRunning {len(VALIDATION_CASES)} Validation Cases...")
    print("="*80)
    
    for i, case in enumerate(VALIDATION_CASES):
        print(f"\nCase {i+1}: {case['category']}")
        print(f"Prompt: \"{case['prompt']}\"")
        print(f"Tool Results: {case['results'][0]['return'] if len(case['results'])==1 else [r['return'] for r in case['results']]}")
        
        try:
            response = generate_response(
                model, 
                processor, 
                case['prompt'], 
                case['tool_calls'], 
                case['results'],
                tools_map
            )
            print("-" * 20)
            print(f"MODEL OUTPUT: \033[92m{response}\033[0m") # Green text
            print("-" * 20)
            print(f"Expected Gist: {case['expected_gist']}")
            
        except Exception as e:
            print(f"ERROR: {e}")
            
    print("\n" + "="*80)
    print("Evaluation Complete.")

if __name__ == "__main__":
    main()
