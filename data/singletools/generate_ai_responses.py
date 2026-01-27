"""
AI Response Generator for Single-Intent JSONC Files

This script loops through all single-intent JSONC files in the singletools directory
and uses an LLM to generate contextually appropriate ai_response fields for each entry.

The LLM is given:
- The user's original prompt
- The intent name and description
- The parts array (showing what entities were extracted)
- The responses array (showing success/failure for each tool call)

This allows the LLM to generate responses that:
1. Match the tone of the original prompt (casual vs formal)
2. Accurately reflect success/failure states
3. Reference the specific entities mentioned (task names, waypoint names, etc.)
4. Feel natural and conversational for an astronaut AI assistant
"""

import os
import re
import json
import http.client
import ssl
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Load environment variables from .env file
load_dotenv()

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent
NAMES_FILE = DATA_DIR / "names.json"
SINGLETOOLS_DIR = SCRIPT_DIR

# =========================
# CONFIGURATION
# =========================

# Max files to process before stopping. Set to -1 to process all files.
MAX_FILES = -1

# Number of parallel API calls to make at once
PARALLEL_WORKERS = 10

# =========================
# LLM PROVIDER SWITCH
# =========================
USE_PRIME_INTELLECT = True   # True => Prime Intellect Inference, False => OpenAI
if USE_PRIME_INTELLECT:
    MODEL_ID = "openai/gpt-4.1-mini"
else:
    MODEL_ID = "gpt-4.1-mini"
MAX_OUTPUT_TOKENS = 100

# Optional: Prime team billing (only used if USE_PRIME_INTELLECT=True)
PRIME_TEAM_ID = os.getenv("PRIME_TEAM_ID")


def load_names_file(filepath: Path) -> dict:
    """
    Parse names.json to extract intent definitions.
    
    Returns a dict mapping intent_name -> {name, description, tokens, return}
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    intents = {}
    for item in data:
        name = item['name']
        intents[name] = item
        intents[name.lower()] = item
        
    return intents


def strip_jsonc_comments(content: str) -> str:
    """
    Remove single-line // comments from JSONC content.
    """
    lines = content.split('\n')
    stripped_lines = []
    for line in lines:
        # Remove // comments (but be careful not to remove // inside strings)
        # Simple approach: only remove if // is at the start or after whitespace
        stripped = re.sub(r'^\s*//.*$', '', line)
        if '//' in stripped:
            # More careful removal - find // not inside quotes
            in_string = False
            result = []
            i = 0
            while i < len(stripped):
                char = stripped[i]
                if char == '"' and (i == 0 or stripped[i-1] != '\\'):
                    in_string = not in_string
                    result.append(char)
                elif char == '/' and i + 1 < len(stripped) and stripped[i+1] == '/' and not in_string:
                    break  # Rest is comment
                else:
                    result.append(char)
                i += 1
            stripped = ''.join(result)
        stripped_lines.append(stripped)
    return '\n'.join(stripped_lines)


def load_jsonc_file(filepath: Path) -> dict:
    """
    Load a JSONC file (JSON with comments).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip comments
    stripped = strip_jsonc_comments(content)
    
    return json.loads(stripped)


def save_jsonc_file(filepath: Path, data: dict, header_comments: list = None):
    """
    Save data as a JSONC file, preserving any header comments.
    """
    content = "{\n"
    
    if header_comments:
        for comment in header_comments:
            content += f"  // {comment}\n"
    
    # Write the data array
    content += f'  "data": {json.dumps(data["data"], indent=4, ensure_ascii=False)}\n'
    content += "}\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def extract_header_comments(filepath: Path) -> list:
    """
    Extract header comments from a JSONC file.
    """
    comments = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith('//'):
                comments.append(stripped[2:].strip())
            elif stripped.startswith('{'):
                continue
            elif stripped.startswith('"data"'):
                break
    return comments


def format_entry_for_prompt(entry: dict, intent_info: dict) -> str:
    """
    Format a single entry as context for the LLM.
    """
    prompt = entry.get('prompt', '')
    parts = entry.get('parts', [])
    responses = entry.get('responses', [])
    
    # Format responses - show success/failure AND any data returned
    response_summary = []
    for i, resp in enumerate(responses):
        intent = resp.get('intent', 'unknown')
        return_val = resp.get('return', False)
        
        # Handle complex return types (like coordinates with {success, x, y, name})
        if isinstance(return_val, dict):
            success = return_val.get('success', False)
            status = "SUCCESS" if success else "FAILED"
            # Include all the data from the return object
            data_parts = [f"{k}={v}" for k, v in return_val.items()]
            data_str = ", ".join(data_parts)
            response_summary.append(f"  Call {i+1}: {intent} -> {status} (data: {data_str})")
        elif isinstance(return_val, bool):
            status = "SUCCESS" if return_val else "FAILED"
            response_summary.append(f"  Call {i+1}: {intent} -> {status}")
        else:
            # For any other return type, show it as data
            response_summary.append(f"  Call {i+1}: {intent} -> returned: {return_val}")
    responses_str = '\n'.join(response_summary)
    
    # Extract entity names from parts for easy reference
    entities = []
    for part in parts:
        if part.get('type') not in ['TEXT', None]:
            entities.append(f"{part.get('type')}: \"{part.get('text', '')}\"")
    entities_str = ', '.join(entities) if entities else 'None (TEXT only)'
    
    return f"""PROMPT: "{prompt}"
ENTITIES: {entities_str}
RESULTS:
{responses_str}"""


def build_single_prompt(entry: dict, intent_info: dict) -> str:
    """
    Build a prompt to generate an ai_response for a single entry.
    """
    intent_name = intent_info.get('name', 'unknown')
    intent_desc = intent_info.get('description', '')
    
    entry_text = format_entry_for_prompt(entry, intent_info)
    
    prompt = f"""You are an AI assistant helping astronauts during EVA (spacewalk) missions. Generate a natural, contextually appropriate spoken response for a voice assistant.

## Intent Being Used
**{intent_name}**: {intent_desc}

## Your Task
Generate a short, natural ai_response that:
1. **Matches the tone** of the original prompt (casual prompts get casual responses, formal get formal)
2. **Reflects the outcome** - celebrate success, acknowledge failures gracefully
3. **References specific entities** when present (task names, waypoint names, coordinates, etc.)
4. **Feels human** - use contractions, be conversational
5. **Is concise** - these are voice responses, keep them brief (1-2 sentences max)

## Response Style Examples
- Casual prompt "yo add task check the rover" + SUCCESS -> "Got it! 'Check the rover' is on your list."
- Formal prompt "Please create waypoint Alpha" + FAILED -> "I wasn't able to create waypoint 'Alpha'. Please try again."
- Question "what's my battery?" + SUCCESS with data -> "Your battery is at 85%."
- Multi-action with partial failure -> "Added 'Task A' but 'Task B' failed."

## Entry to Process
{entry_text}

## Output Format
Return ONLY the ai_response string. No quotes, no JSON, no explanation - just the response text itself."""

    return prompt


def call_chat_completions(prompt: str) -> str:
    """
    Call either OpenAI or Prime Intellect Inference (OpenAI-compatible) using raw HTTP.
    """
    context = ssl.create_default_context()

    if USE_PRIME_INTELLECT:
        host = "api.pinference.ai"
        path = "/api/v1/chat/completions"
        api_key = os.getenv("PI_KEY")
        if not api_key:
            raise Exception("PI_KEY not found (set it in .env)")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if PRIME_TEAM_ID:
            headers["X-Prime-Team-ID"] = PRIME_TEAM_ID
    else:
        host = "api.openai.com"
        path = "/v1/chat/completions"
        api_key = os.getenv("OPENAI_KEY")
        if not api_key:
            raise Exception("OPENAI_KEY not found (set it in .env)")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    conn = http.client.HTTPSConnection(host, context=context)

    payload = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": "You are a training data generator for an AI assistant that helps astronauts during EVA missions. Generate natural, contextually appropriate voice responses."
            },
            {"role": "user", "content": prompt},
        ],
    }

    if USE_PRIME_INTELLECT:
        payload["max_tokens"] = MAX_OUTPUT_TOKENS
    else:
        payload["max_completion_tokens"] = MAX_OUTPUT_TOKENS

    conn.request("POST", path, body=json.dumps(payload), headers=headers)
    response = conn.getresponse()

    raw = response.read().decode("utf-8")
    conn.close()

    if response.status != 200:
        raise Exception(f"API error ({response.status}): {raw}")

    response_data = json.loads(raw)
    
    # Debug: check what's in the response
    if "choices" not in response_data or len(response_data["choices"]) == 0:
        raise Exception(f"No choices in response: {raw[:500]}")
    
    content = response_data["choices"][0]["message"]["content"]
    if not content:
        raise Exception(f"Empty content in response: {raw[:500]}")
    
    return content


def process_single_entry(entry_info: tuple) -> tuple:
    """
    Process a single entry and return the generated response.
    Returns (index, response, error_message)
    """
    index, entry, intent_info = entry_info
    prompt_text = entry.get('prompt', '<no prompt>')[:50]
    
    try:
        print(f"    [DEBUG] Entry {index}: Building prompt for '{prompt_text}'...")
        user_prompt = build_single_prompt(entry, intent_info)
        print(f"    [DEBUG] Entry {index}: Calling API...")
        response = call_chat_completions(user_prompt)
        print(f"    [DEBUG] Entry {index}: Raw API response: '{response[:100] if response else '<NONE>'}...'")
        
        # Clean up response - remove any quotes or extra whitespace
        if response:
            response = response.strip()
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
            print(f"    [DEBUG] Entry {index}: Cleaned response: '{response[:100]}'")
        else:
            print(f"    [WARN] Entry {index}: API returned empty/None response!")
            return (index, None, "API returned empty response")
        
        if not response:
            return (index, None, "Response was empty after cleaning")
            
        return (index, response, None)
        
    except Exception as e:
        print(f"    [ERROR] Entry {index}: Exception - {e}")
        return (index, None, str(e))


def process_file(filepath: Path, intents: dict, dry_run: bool = False) -> str:
    """
    Process a single JSONC file, adding ai_response fields to entries that don't have them.
    """
    filename = filepath.name
    
    try:
        # Load the file
        data = load_jsonc_file(filepath)
        header_comments = extract_header_comments(filepath)
        
        if 'data' not in data:
            return f"SKIP {filename}: No 'data' field found"
        
        entries = data['data']
        
        # Find entries that need ai_response
        entries_to_process = []
        indices_to_process = []
        
        for i, entry in enumerate(entries):
            if 'ai_response' not in entry or not entry['ai_response']:
                entries_to_process.append(entry)
                indices_to_process.append(i)
        
        if not entries_to_process:
            return f"SKIP {filename}: All entries already have ai_response"
        
        # Get intent info from filename (remove .jsonc extension)
        intent_name = filepath.stem
        intent_info = intents.get(intent_name.lower(), {
            'name': intent_name,
            'description': f'Intent: {intent_name}'
        })
        
        if dry_run:
            return f"DRY RUN {filename}: Would process {len(entries_to_process)}/{len(entries)} entries"
        
        # Build list of entries to process
        entry_tasks = [
            (idx, entry, intent_info) 
            for idx, entry in zip(indices_to_process, entries_to_process)
        ]
        
        # Process entries in parallel
        all_responses = {}
        errors = []
        
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {
                executor.submit(process_single_entry, task): task[0] 
                for task in entry_tasks
            }
            
            for future in as_completed(futures):
                index, response, error = future.result()
                print(f"  [RESULT] Entry {index}: response={repr(response)[:60]}, error={error}")
                if error:
                    errors.append(f"Entry {index}: {error}")
                elif response:
                    all_responses[index] = response
                else:
                    errors.append(f"Entry {index}: Got no response and no error")
                    print(f"  [WARN] Entry {index}: Neither response nor error - this shouldn't happen!")
        
        # Apply responses to entries
        updates_made = 0
        for idx, response in all_responses.items():
            entries[idx]['ai_response'] = response
            updates_made += 1
        
        # Save the updated file
        data['data'] = entries
        save_jsonc_file(filepath, data, header_comments)
        
        # Only count as COMPLETE if ALL entries were processed successfully
        if updates_made == len(entries_to_process):
            return f"COMPLETE {filename}: Updated all {updates_made} entries"
        else:
            return f"PARTIAL {filename}: Updated {updates_made}/{len(entries_to_process)} entries ({len(errors)} errors)"
        
    except Exception as e:
        return f"ERROR {filename}: {e}"


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate ai_response fields for single-intent JSONC files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without making changes')
    parser.add_argument('--file', type=str, help='Process only a specific file (basename)')
    args = parser.parse_args()
    
    # Load intent definitions
    print("Loading names.json...")
    intents = load_names_file(NAMES_FILE)
    print(f"Loaded {len(intents) // 2} intent definitions")
    
    # Find all JSONC files in singletools directory
    jsonc_files = list(SINGLETOOLS_DIR.glob("*.jsonc"))
    print(f"Found {len(jsonc_files)} JSONC files")
    
    if args.file:
        # Filter to specific file
        jsonc_files = [f for f in jsonc_files if f.name == args.file or f.stem == args.file]
        if not jsonc_files:
            print(f"File not found: {args.file}")
            return
    
    # Process files
    if args.dry_run:
        print("\n=== DRY RUN MODE ===\n")
    
    if MAX_FILES >= 0:
        print(f"Will stop after editing {MAX_FILES} files (set MAX_FILES=-1 to process all)")
    
    # Process files sequentially - BLOCK on each file until fully complete
    files_completed = 0
    for filepath in jsonc_files:
        # Keep processing this file until it's complete or we give up
        while True:
            result = process_file(filepath, intents, args.dry_run)
            print(result)
            
            if result.startswith("SKIP"):
                # Already done, move to next file
                break
            elif result.startswith("COMPLETE"):
                # Successfully finished this file
                files_completed += 1
                break
            elif result.startswith("ERROR"):
                # Something went wrong, stop entirely
                print(f"Stopping due to error on {filepath.name}")
                return
            else:
                # PARTIAL - keep going on this same file
                print(f"  Continuing to process {filepath.name}...")
                continue
        
        # Check if we've hit the MAX_FILES limit
        if MAX_FILES >= 0 and files_completed >= MAX_FILES:
            print(f"\nStopped after fully completing {MAX_FILES} file(s)")
            break
    
    print(f"\nDone! Fully completed {files_completed} file(s).")


if __name__ == "__main__":
    main()
