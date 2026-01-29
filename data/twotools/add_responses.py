#!/usr/bin/env python3
"""
Add responses field to two-tool combo files.

For each entry in the twotools/*.jsonc files:
1. Look up the return schema for each intent in tool_calls
2. Generate realistic return values based on the schema
3. Add a 'responses' array with {intent, return} for each tool call
"""

import os
import re
import json
import random
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent
NAMES_FILE = DATA_DIR / "names.json"
TWOTOOLS_DIR = SCRIPT_DIR

# Intents that involve searching for something (can fail with "not found")
SEARCH_INTENTS = {
    'Complete_task',
    'Delete_task', 
    'Delete_waypoint',
    'Get_coordinates',
    'Set_navigation_target',
}

# Map intent to the type name for "not found" messages
INTENT_TO_TYPE = {
    'Complete_task': 'task',
    'Delete_task': 'task',
    'Delete_waypoint': 'waypoint',
    'Get_coordinates': 'waypoint',
    'Set_navigation_target': 'waypoint',
}

# Map intent (lowercase) -> the EXACT part type used in data files
# Each intent has its OWN specific part type:
# - Add_task uses TASK_NAME
# - Complete_task uses COMPLETE_TASK_NAME (NOT TASK_NAME!)
# - Delete_task uses DELETE_TASK_NAME (NOT TASK_NAME!)
# - Add_waypoint uses WAYPOINT_NAME
# - Delete_waypoint uses DELETE_WAYPOINT_NAME (NOT WAYPOINT_NAME!)
# - Get_coordinates uses COORDINATE_TARGET_NAME
# - Set_navigation_target uses NAVIGATION_TARGET_NAME
#
# NO FALLBACKS - each intent must match its exact part type
INTENT_TO_PART_TYPE = {
    'add_task': 'TASK_NAME',
    'complete_task': 'COMPLETE_TASK_NAME',
    'delete_task': 'DELETE_TASK_NAME',
    'add_waypoint': 'WAYPOINT_NAME',
    'delete_waypoint': 'DELETE_WAYPOINT_NAME',
    'get_coordinates': 'COORDINATE_TARGET_NAME',
    'set_navigation_target': 'NAVIGATION_TARGET_NAME',
}


def load_names_file(filepath: Path) -> dict:
    """Load names.json and return dict mapping intent_name (lowercase) -> schema."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    intents = {}
    for item in data:
        name = item['name']
        intents[name.lower()] = item
    return intents


def strip_comments(text: str) -> str:
    """Remove // comments from JSONC."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        in_string = False
        escape_next = False
        result = []
        i = 0
        while i < len(line):
            char = line[i]
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            if char == '\\' and in_string:
                result.append(char)
                escape_next = True
                i += 1
                continue
            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            if not in_string and i + 1 < len(line) and line[i:i+2] == '//':
                break
            result.append(char)
            i += 1
        cleaned.append(''.join(result))
    return '\n'.join(cleaned)


def extract_header_comments(filepath: Path) -> str:
    """Extract the header comments from a JSONC file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    header_lines = []
    brace_found = False
    
    for line in lines:
        stripped = line.strip()
        if stripped == '{':
            brace_found = True
            continue
        if brace_found:
            if stripped.startswith('//'):
                header_lines.append(line)
            elif stripped.startswith('"data"'):
                break
            elif stripped:
                break
    
    return '\n'.join(header_lines) + '\n' if header_lines else ''


def extract_name_from_parts(parts: list, intent: str) -> str:
    """Extract the relevant name from parts based on intent.
    
    CRITICAL: Each intent has its OWN specific part type.
    When processing 'add task X and complete Y':
    - Add_task looks for TASK_NAME -> finds 'X'
    - Complete_task looks for COMPLETE_TASK_NAME -> finds 'Y'
    
    We do NOT fall back from COMPLETE_TASK_NAME to TASK_NAME!
    Each intent must match its exact part type.
    """
    target_type = INTENT_TO_PART_TYPE.get(intent.lower())
    if not target_type:
        return None
    
    for part in parts:
        if part.get('type') == target_type:
            return part.get('text')
    return None


def get_failure_reason(intent: str, name: str = None) -> str:
    """Get the appropriate failure reason for an intent."""
    if intent in SEARCH_INTENTS:
        # 50/50 split between "not found" and "server error"
        if random.random() < 0.5:
            type_name = INTENT_TO_TYPE.get(intent, 'item')
            if name:
                return f"{type_name} '{name}' not found"
            return f"{type_name} not found"
        else:
            return "server error"
    else:
        return "server error"


def generate_return_value(intent_schema: dict, entry: dict, intent_name: str) -> any:
    """Generate a return value based on the intent's return schema."""
    return_info = intent_schema.get('return', {})
    return_type = return_info.get('type', 'boolean')
    
    # Get name from parts if applicable
    parts = entry.get('parts', [])
    name = extract_name_from_parts(parts, intent_name)
    
    # Determine success/failure (85% success rate typically)
    is_success = random.random() < 0.85
    
    if return_type == 'boolean':
        return is_success
    
    elif return_type == 'number':
        if is_success:
            range_vals = return_info.get('range', [0, 100])
            return round(random.uniform(range_vals[0], range_vals[1]), 1)
        else:
            return False  # Number intents don't really fail, but just in case
    
    elif return_type == 'array':
        # For get_warnings - return array of warning strings
        possible_warnings = [
            "battery time remaining below 2 hours",
            "oxygen primary storage at 25%",
            "heart rate elevated",
            "coolant temperature above nominal",
            "CO2 scrubber A near capacity",
            "suit pressure slightly low",
            "secondary fan RPM below threshold"
        ]
        num_warnings = random.choice([0, 0, 1, 1, 1, 2, 2, 3])
        return random.sample(possible_warnings, min(num_warnings, len(possible_warnings)))
    
    elif return_type == 'object':
        # Complex return types - depends on the intent
        intent_lower = intent_name.lower()
        
        if 'coordinates' in intent_lower:
            if is_success:
                return {
                    'success': True,
                    'x': round(random.uniform(-10000, 10000), 1),
                    'y': round(random.uniform(-10000, 10000), 1),
                    'name': name or 'target'
                }
            else:
                return {
                    'success': False,
                    'failure_reason': get_failure_reason(intent_name, name),
                    'x': 0,
                    'y': 0,
                    'name': ''
                }
        
        elif 'navigation' in intent_lower:
            if is_success:
                return {
                    'success': True,
                    'target_name': name or 'destination'
                }
            else:
                return {
                    'success': False,
                    'failure_reason': get_failure_reason(intent_name, name),
                    'target_name': ''
                }
        
        elif any(x in intent_lower for x in ['complete_task', 'delete_task', 'delete_waypoint']):
            if is_success:
                return {
                    'success': True,
                    'name': name or 'item'
                }
            else:
                return {
                    'success': False,
                    'failure_reason': get_failure_reason(intent_name, name),
                    'name': ''
                }
        
        else:
            # Generic object
            if is_success:
                return {'success': True}
            else:
                return {'success': False, 'failure_reason': 'server error'}
    
    elif return_type == 'void':
        return None
    
    else:
        # Default to boolean
        return is_success


def process_file(filepath: Path, intents: dict) -> tuple:
    """Process a single JSONC file. Returns (modified_count, skipped_count)."""
    print(f"Processing: {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse JSONC
    try:
        cleaned = strip_comments(content)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  ERROR parsing {filepath.name}: {e}")
        return 0, 0
    
    entries = data.get('data', [])
    modified_count = 0
    skipped_count = 0
    
    for entry in entries:
        # Skip if already has responses
        if 'responses' in entry and entry['responses']:
            skipped_count += 1
            continue
        
        tool_calls = entry.get('tool_calls', [])
        if not tool_calls:
            continue
        
        # Generate responses for each tool call
        responses = []
        for tool_call in tool_calls:
            tool_call_lower = tool_call.lower()
            
            if tool_call_lower not in intents:
                print(f"  WARNING: Unknown intent '{tool_call}' in {filepath.name}")
                continue
            
            intent_schema = intents[tool_call_lower]
            return_value = generate_return_value(intent_schema, entry, tool_call)
            
            responses.append({
                'intent': tool_call,
                'return': return_value
            })
        
        if responses:
            entry['responses'] = responses
            modified_count += 1
    
    # Extract header comments for preserving format
    header_comments = extract_header_comments(filepath)
    
    # Write back
    if modified_count > 0:
        # Build output with header comments preserved
        output = '{\n'
        output += header_comments
        output += f'  "data": {json.dumps(entries, indent=4)}\n'
        output += '}\n'
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"  Added responses to {modified_count} entries (skipped {skipped_count})")
    else:
        print(f"  No modifications needed ({skipped_count} already had responses)")
    
    return modified_count, skipped_count


def main():
    random.seed(42)  # For reproducibility
    
    # Load intent definitions
    print("Loading names.json...")
    intents = load_names_file(NAMES_FILE)
    print(f"Loaded {len(intents)} intent definitions")
    
    # Find all JSONC files in twotools directory
    jsonc_files = list(TWOTOOLS_DIR.glob('*AND*.jsonc'))
    print(f"Found {len(jsonc_files)} two-tool combo files\n")
    
    total_modified = 0
    total_skipped = 0
    
    for filepath in sorted(jsonc_files):
        modified, skipped = process_file(filepath, intents)
        total_modified += modified
        total_skipped += skipped
    
    print(f"\n{'='*50}")
    print(f"SUMMARY:")
    print(f"  Total files processed: {len(jsonc_files)}")
    print(f"  Total entries with responses added: {total_modified}")
    print(f"  Total entries skipped (already had responses): {total_skipped}")


if __name__ == '__main__':
    main()
