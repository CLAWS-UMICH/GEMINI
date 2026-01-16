TODO: CHECK THE MULTI PARAM TOOL GENERATION BEFOER MASS RUNNING

"""
Two-Tool Combo Data Generator

Reads intent combinations from intentcombos.txt, looks up their descriptions and token labels
from names.txt, then calls OpenAI API to generate 50 training prompts that combine both intents.
"""

import os
import re
import json
import http.client
import ssl
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables from .env file
load_dotenv()

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent
NAMES_FILE = DATA_DIR / "names.txt"
INTENT_COMBOS_FILE = SCRIPT_DIR / "intentcombos.txt"
OUTPUT_DIR = SCRIPT_DIR

# Number of parallel API calls to make at once
PARALLEL_WORKERS = 50

# ============================================================================
# SPECIAL TOKEN CONFIGURATION
# Maps intent name (lowercase) to its special token label and example text.
# The examples include both single-param and MULTI-param variations.
# ============================================================================
SPECIAL_TOKEN_CONFIG = {
    "get_coordinates": {
        "token": "COORDINATE_TARGET_NAME",
        "text": """- **Get_coordinates** uses COORDINATE_TARGET_NAME for the target being located:
  Single: "where is the LTV" -> parts: [{{"type":"TEXT","text":"where is the "}},{{"type":"COORDINATE_TARGET_NAME","text":"LTV"}}]
  Multi: "get coordinates for the rock and the crater" -> parts: [{{"type":"TEXT","text":"get coordinates for the "}},{{"type":"COORDINATE_TARGET_NAME","text":"rock"}},{{"type":"TEXT","text":" and the "}},{{"type":"COORDINATE_TARGET_NAME","text":"crater"}}]"""
    },
    "set_navigation_target": {
        "token": "NAVIGATION_TARGET_NAME",
        "text": """- **Set_navigation_target** uses NAVIGATION_TARGET_NAME for the destination:
  Single: "navigate to the rover" -> parts: [{{"type":"TEXT","text":"navigate to the "}},{{"type":"NAVIGATION_TARGET_NAME","text":"rover"}}]
  Multi: "navigate to the rover and then to base camp" -> parts: [{{"type":"TEXT","text":"navigate to the "}},{{"type":"NAVIGATION_TARGET_NAME","text":"rover"}},{{"type":"TEXT","text":" and then to "}},{{"type":"NAVIGATION_TARGET_NAME","text":"base camp"}}]"""
    },
    "add_waypoint": {
        "token": "WAYPOINT_NAME",
        "text": """- **Add_waypoint** uses WAYPOINT_NAME for the marker name:
  Single: "mark this spot as crater edge" -> parts: [{{"type":"TEXT","text":"mark this spot as "}},{{"type":"WAYPOINT_NAME","text":"crater edge"}}]
  Multi: "add waypoints Alpha and Bravo" -> parts: [{{"type":"TEXT","text":"add waypoints "}},{{"type":"WAYPOINT_NAME","text":"Alpha"}},{{"type":"TEXT","text":" and "}},{{"type":"WAYPOINT_NAME","text":"Bravo"}}]
  Multi (3): "drop pins at Start, Middle, and End" -> parts: [{{"type":"TEXT","text":"drop pins at "}},{{"type":"WAYPOINT_NAME","text":"Start"}},{{"type":"TEXT","text":", "}},{{"type":"WAYPOINT_NAME","text":"Middle"}},{{"type":"TEXT","text":", and "}},{{"type":"WAYPOINT_NAME","text":"End"}}]"""
    },
    "delete_waypoint": {
        "token": "WAYPOINT_NAME",
        "text": """- **delete_waypoint** uses WAYPOINT_NAME for the marker to remove:
  Single: "remove waypoint old camp" -> parts: [{{"type":"TEXT","text":"remove waypoint "}},{{"type":"WAYPOINT_NAME","text":"old camp"}}]
  Multi: "delete waypoints X and Y" -> parts: [{{"type":"TEXT","text":"delete waypoints "}},{{"type":"WAYPOINT_NAME","text":"X"}},{{"type":"TEXT","text":" and "}},{{"type":"WAYPOINT_NAME","text":"Y"}}]"""
    },
    "add_task": {
        "token": "TASK_NAME",
        "text": """- **Add_task** uses TASK_NAME for the task content:
  Single: "add task check oxygen levels" -> parts: [{{"type":"TEXT","text":"add task "}},{{"type":"TASK_NAME","text":"check oxygen levels"}}]
  Multi: "add task A and task B" -> parts: [{{"type":"TEXT","text":"add task "}},{{"type":"TASK_NAME","text":"A"}},{{"type":"TEXT","text":" and task "}},{{"type":"TASK_NAME","text":"B"}}]
  Multi (3): "create tasks: inspect hatch, test seal, log results" -> parts: [{{"type":"TEXT","text":"create tasks: "}},{{"type":"TASK_NAME","text":"inspect hatch"}},{{"type":"TEXT","text":", "}},{{"type":"TASK_NAME","text":"test seal"}},{{"type":"TEXT","text":", "}},{{"type":"TASK_NAME","text":"log results"}}]"""
    },
    "delete_task": {
        "token": "TASK_NAME",
        "text": """- **Delete_task** uses TASK_NAME for the task to remove:
  Single: "remove task battery check" -> parts: [{{"type":"TEXT","text":"remove task "}},{{"type":"TASK_NAME","text":"battery check"}}]
  Multi: "delete task X and task Y" -> parts: [{{"type":"TEXT","text":"delete task "}},{{"type":"TASK_NAME","text":"X"}},{{"type":"TEXT","text":" and task "}},{{"type":"TASK_NAME","text":"Y"}}]"""
    },
    "complete_task": {
        "token": "TASK_NAME",
        "text": """- **Complete_task** uses TASK_NAME for the task being completed:
  Single: "mark antenna check as done" -> parts: [{{"type":"TEXT","text":"mark "}},{{"type":"TASK_NAME","text":"antenna check"}},{{"type":"TEXT","text":" as done"}}]
  Multi: "finish task Alpha and task Beta" -> parts: [{{"type":"TEXT","text":"finish task "}},{{"type":"TASK_NAME","text":"Alpha"}},{{"type":"TEXT","text":" and task "}},{{"type":"TASK_NAME","text":"Beta"}}]"""
    },
}


def parse_names_file(filepath: Path) -> dict:
    """
    Parse names.txt to extract intent definitions.
    
    Returns a dict mapping intent_name -> {description: str, tokens: str}
    """
    intents = {}
    current_intent = None
    current_description = None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for intent name (wrapped in **)
        match = re.match(r'\*\*(\w+)\*\*', line)
        if match:
            current_intent = match.group(1)
            i += 1
            
            # Next line is the description
            if i < len(lines):
                current_description = lines[i].strip()
                i += 1
            
            # Next line is the tokens
            if i < len(lines):
                tokens = lines[i].strip()
                intents[current_intent.lower()] = {
                    'name': current_intent,
                    'description': current_description,
                    'tokens': tokens
                }
                # Also store with original case for lookups
                intents[current_intent] = intents[current_intent.lower()]
                i += 1
        else:
            i += 1
    
    return intents


def read_intent_combos(filepath: Path) -> list:
    """
    Read intentcombos.txt and return list of (intent1, intent2) tuples.
    """
    combos = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and ',' in line:
                parts = line.split(',')
                if len(parts) == 2:
                    combos.append((parts[0].strip(), parts[1].strip()))
    return combos


def build_prompt(intent1_info: dict, intent2_info: dict) -> str:
    """
    Build the prompt for OpenAI API to generate combined intent training data.
    """
    # Combine token types from both intents (unique set)
    tokens1 = set(t.strip() for t in intent1_info['tokens'].split(','))
    tokens2 = set(t.strip() for t in intent2_info['tokens'].split(','))
    all_tokens = sorted(tokens1 | tokens2)
    
    # Build special token instructions based on which intents we have (using config)
    special_token_examples = []
    
    intent1_name_lower = intent1_info['name'].lower()
    intent2_name_lower = intent2_info['name'].lower()
    
    # Check each intent against the config
    for intent_key, config in SPECIAL_TOKEN_CONFIG.items():
        if intent_key in intent1_name_lower or intent_key in intent2_name_lower:
            special_token_examples.append(config["text"])
    
    special_token_section = ""
    if special_token_examples:
        special_token_section = "\n\n## CRITICAL: Token Label Examples (Including Multi-Parameter Patterns)\n" + "\n\n".join(special_token_examples)
    
    prompt = f"""Your job is to generate HIGH quality, EXTREMELY diverse training data for a model that needs to recognize prompts that combine TWO intents in a single user utterance.

## Intent 1: {intent1_info['name']}
Description: {intent1_info['description']}
Allowed token labels: {intent1_info['tokens']}

## Intent 2: {intent2_info['name']}
Description: {intent2_info['description']}
Allowed token labels: {intent2_info['tokens']}
{special_token_section}

## CRITICAL DIVERSITY REQUIREMENTS (FOLLOW THESE EXACTLY):

### 1. INTENT ORDERING - MANDATORY VARIATION:
- Approximately 25 prompts should mention Intent 1's action/query FIRST, then Intent 2
- Approximately 25 prompts should mention Intent 2's action/query FIRST, then Intent 1
- Mix up which intent comes first throughout the list - DO NOT group them

### 2. MULTI-PARAMETER ACTIONS (When Applicable):
- For intents that take parameters, include examples with 1, 2, or 3+ items in a single utterance.
- See the Token Label Examples section above for specific patterns.

### 3. SENTENCE LENGTH - MANDATORY VARIATION:
- ~10 prompts should be SHORT (4-7 words): "check battery and open vitals"
- ~20 prompts should be MEDIUM (8-12 words): "can you tell me my battery level and also show the vitals menu"
- ~20 prompts should be LONG (13-20 words): "hey I need you to pull up my current battery time remaining and while you're at it open up the vitals display"

### 4. SENTENCE STRUCTURE - MANDATORY VARIATION:
- Direct commands: "check X and do Y"
- Questions: "what's my X and can you show Y?"
- Casual/conversational: "yo check X and also Y please"
- Formal requests: "please provide X and additionally display Y"
- Implied commands: "need X and Y"
- Compound with conditions: "after checking X, show me Y"

### 5. CONNECTOR WORDS - USE ALL OF THESE ACROSS YOUR 50 PROMPTS:
and, then, also, plus, while, after, before, but first, as well as, along with, in addition, additionally, meanwhile, oh and, and then, followed by, next, at the same time

### 6. VOCABULARY - MANDATORY VARIATION:
- Mix formal and informal language
- Use different verbs for the same action (show/display/pull up/open/bring up)
- Use different ways to refer to the same thing (battery/power/charge, vitals/biometrics/suit data)
- Include casual speech patterns ("yo", "hey", "gimme", "lemme")
- Include professional speech patterns ("please", "could you", "I need")

## ABSOLUTE REQUIREMENTS:
1. Generate EXACTLY 50 prompts
2. EVERY SINGLE PROMPT MUST MAKE LOGICAL SENSE - an astronaut would realistically say this
3. NO TWO PROMPTS should look alike - if they're too similar, regenerate
4. Both intents MUST be clearly present in each prompt
5. You MUST only use these token labels: {', '.join(all_tokens)}

## Output Format:
Return a JSON array of 50 objects. Each object must have:
- "prompt": the user's spoken command/question
- "tool_calls": List of intent names matching the actions in the prompt. Example: ["{intent1_info['name']}", "{intent2_info['name']}"] OR ["{intent1_info['name']}", "{intent1_info['name']}", "{intent2_info['name']}"]
- "parts": array of token parts, where each part has "type" (one of the allowed labels) and "text"

For intents that ONLY use TEXT tokens, the entire prompt goes in one TEXT part.
For intents with named parameters (TASK_NAME, WAYPOINT_NAME, NAVIGATION_TARGET_NAME, COORDINATE_TARGET_NAME), you MUST properly segment the parts to separate TEXT from the parameter tokens. The parameter value should be in its own part with the correct type.

IMPORTANT: Return ONLY the JSON array, no markdown code blocks or additional text. The response must be valid JSON."""

    return prompt


def call_openai_api(prompt: str, api_key: str) -> str:
    """
    Call OpenAI API using raw HTTP (no library).
    """
    # Create SSL context
    context = ssl.create_default_context()
    
    # Connect to OpenAI API
    conn = http.client.HTTPSConnection("api.openai.com", context=context)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        # "model": "gpt-5-mini-2025-08-07",
        "model":"gpt-5.2-2025-12-11",
        "messages": [
            {
                "role": "system",
                "content": "You are a training data generator for an AI assistant that helps astronauts during EVA missions. Generate high-quality, diverse training examples."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_completion_tokens": 16000
    }
    
    conn.request("POST", "/v1/chat/completions", json.dumps(payload), headers)
    response = conn.getresponse()
    
    if response.status != 200:
        error_body = response.read().decode('utf-8')
        raise Exception(f"OpenAI API error: {response.status} - {error_body}")
    
    response_data = json.loads(response.read().decode('utf-8'))
    conn.close()
    
    return response_data['choices'][0]['message']['content']


def validate_data(data: list, intent1_info: dict, intent2_info: dict) -> tuple:
    """
    Validate that all items in data use only allowed tool_calls and token labels.
    
    Returns (is_valid, error_messages)
    """
    # Build allowed sets
    allowed_intents = {intent1_info['name'].lower(), intent2_info['name'].lower()}
    
    tokens1 = set(t.strip() for t in intent1_info['tokens'].split(','))
    tokens2 = set(t.strip() for t in intent2_info['tokens'].split(','))
    allowed_tokens = tokens1 | tokens2
    
    errors = []
    
    for idx, item in enumerate(data):
        # Check tool_calls
        if 'tool_calls' in item:
            for tool_call in item['tool_calls']:
                if tool_call.lower() not in allowed_intents:
                    errors.append(f"Item {idx}: Invalid tool_call '{tool_call}' (allowed: {allowed_intents})")
        else:
            errors.append(f"Item {idx}: Missing 'tool_calls' field")
        
        # Check parts token types
        if 'parts' in item:
            for part_idx, part in enumerate(item['parts']):
                if 'type' in part:
                    if part['type'] not in allowed_tokens:
                        errors.append(f"Item {idx}, part {part_idx}: Invalid token type '{part['type']}' (allowed: {allowed_tokens})")
                else:
                    errors.append(f"Item {idx}, part {part_idx}: Missing 'type' field")
        else:
            errors.append(f"Item {idx}: Missing 'parts' field")
        
        # Check prompt exists
        if 'prompt' not in item:
            errors.append(f"Item {idx}: Missing 'prompt' field")
    
    return (len(errors) == 0, errors)


def save_jsonc_file(filepath: Path, intent1_info: dict, intent2_info: dict, data: list):
    """
    Save the generated data as a JSONC file with comments at the top.
    """
    # Combine token types
    tokens1 = set(t.strip() for t in intent1_info['tokens'].split(','))
    tokens2 = set(t.strip() for t in intent2_info['tokens'].split(','))
    all_tokens = sorted(tokens1 | tokens2)
    
    content = f"""{{
  // intents: {intent1_info['name']} AND {intent2_info['name']}
  // description_1: {intent1_info['description']}
  // description_2: {intent2_info['description']}
  // tokens: {', '.join(all_tokens)}
  "data": {json.dumps(data, indent=4)}
}}
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def process_combo(combo_info: tuple) -> str:
    """
    Process a single intent combo. Returns a status message.
    """
    idx, total, intent1, intent2, intent1_info, intent2_info, output_path, api_key = combo_info
    output_filename = output_path.name
    
    try:
        # Build prompt
        prompt = build_prompt(intent1_info, intent2_info)
        
        # Call OpenAI API
        response = call_openai_api(prompt, api_key)
        
        # Parse response as JSON
        # Handle potential markdown code blocks
        response = response.strip()
        if response.startswith('```'):
            # Remove markdown code block
            lines = response.split('\n')
            response = '\n'.join(lines[1:-1])
        
        data = json.loads(response)
        
        # Warning for count mismatch
        count_warning = ""
        if len(data) != 50:
            count_warning = f" (Warning: Got {len(data)} items instead of 50)"
        
        # Validate tool_calls and token labels
        is_valid, validation_errors = validate_data(data, intent1_info, intent2_info)
        if not is_valid:
            error_summary = "; ".join(validation_errors[:3])
            if len(validation_errors) > 3:
                error_summary += f" ... and {len(validation_errors) - 3} more"
            return f"[{idx}/{total}] VALIDATION FAILED {output_filename}: {error_summary}"
        
        # Save to file
        save_jsonc_file(output_path, intent1_info, intent2_info, data)
        return f"[{idx}/{total}] Saved {output_filename}{count_warning}"
        
    except json.JSONDecodeError as e:
        return f"[{idx}/{total}] JSON ERROR {output_filename}: {e}"
    except Exception as e:
        return f"[{idx}/{total}] ERROR {output_filename}: {e}"


def main():
    # Get API key
    api_key = os.getenv('OPENAI_KEY')
    if not api_key:
        print("Error: OPENAI_KEY not found in environment variables or .env file")
        return
    
    # Parse names.txt
    print("Parsing names.txt...")
    intents = parse_names_file(NAMES_FILE)
    print(f"Found {len(intents) // 2} intents")  # Divided by 2 because we store both cases
    
    # Read intent combos
    print("Reading intent combinations...")
    combos = read_intent_combos(INTENT_COMBOS_FILE)
    print(f"Found {len(combos)} intent combinations")
    print(f"Using {PARALLEL_WORKERS} parallel workers")
    
    # Build list of combos to process
    tasks_to_process = []
    skipped = 0
    
    for i, (intent1, intent2) in enumerate(combos):
        output_filename = f"{intent1}AND{intent2}.jsonc"
        output_path = OUTPUT_DIR / output_filename
        
        # Skip if already exists
        if output_path.exists():
            skipped += 1
            continue
        
        # Look up intent info (case-insensitive)
        intent1_lower = intent1.lower()
        intent2_lower = intent2.lower()
        
        if intent1_lower not in intents:
            print(f"Warning: Intent '{intent1}' not found in names.txt, skipping")
            continue
        if intent2_lower not in intents:
            print(f"Warning: Intent '{intent2}' not found in names.txt, skipping")
            continue
        
        intent1_info = intents[intent1_lower]
        intent2_info = intents[intent2_lower]
        
        tasks_to_process.append((
            len(tasks_to_process) + 1,  # idx (1-based among tasks to process)
            len(combos) - skipped,  # total to process (estimated)
            intent1,
            intent2,
            intent1_info,
            intent2_info,
            output_path,
            api_key
        ))
    
    print(f"Skipped {skipped} already existing files")
    print(f"Processing {len(tasks_to_process)} remaining combinations...")
    
    if not tasks_to_process:
        print("Nothing to process!")
        return
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {executor.submit(process_combo, task): task for task in tasks_to_process}
        
        for future in as_completed(futures):
            result = future.result()
            print(result)


if __name__ == "__main__":
    main()
