#!/usr/bin/env python3
"""
Script to add failure_reason to all return objects with success: false.

Rules:
1. If return is a boolean false -> convert to {success: false, failure_reason: "server error"}
2. If return is an object with success: false:
   - For search intents (Complete_task, Delete_task, Delete_waypoint): 
     50/50 split between "[type] not found" and "server error"
   - For all other intents: "server error"
"""

import os
import re
import json
import random
from pathlib import Path

# Intents that involve searching for something
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

def strip_comments(text: str) -> str:
    """Remove // comments from JSONC."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        # Find // that's not inside a string
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


def get_failure_reason(intent: str, name: str = None) -> str:
    """Get the appropriate failure reason for an intent."""
    if intent in SEARCH_INTENTS:
        # 50/50 split
        if random.random() < 0.5:
            type_name = INTENT_TO_TYPE.get(intent, 'item')
            if name:
                return f"{type_name} '{name}' not found"
            return f"{type_name} not found"
        else:
            return "server error"
    else:
        return "server error"


def extract_name_from_parts(parts: list, intent: str) -> str:
    """Try to extract the relevant name from parts based on intent."""
    # Map intent to the part type we're looking for
    part_type_map = {
        'Complete_task': 'TASK_NAME',
        'Delete_task': 'DELETE_TASK_NAME',
        'Delete_waypoint': 'DELETE_WAYPOINT_NAME',
        'Get_coordinates': 'COORDINATE_TARGET_NAME',
        'Set_navigation_target': 'NAVIGATION_TARGET_NAME',
    }
    
    target_type = part_type_map.get(intent)
    if not target_type:
        return None
    
    for part in parts:
        if part.get('type') == target_type:
            return part.get('text')
    return None


def process_file(filepath: Path) -> tuple:
    """Process a single JSONC file. Returns (modified_count, total_false_returns)."""
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
    total_false = 0
    
    for entry in entries:
        parts = entry.get('parts', [])
        responses = entry.get('responses', [])
        
        for i, resp in enumerate(responses):
            intent = resp.get('intent', 'unknown')
            return_val = resp.get('return')
            
            # Case 1: return is a boolean false
            if return_val is False:
                total_false += 1
                failure_reason = get_failure_reason(intent, extract_name_from_parts(parts, intent))
                resp['return'] = {
                    'success': False,
                    'failure_reason': failure_reason
                }
                modified_count += 1
                
            # Case 2: return is an object with success: false
            elif isinstance(return_val, dict) and return_val.get('success') is False:
                total_false += 1
                if 'failure_reason' not in return_val:
                    # Try to get name from the return object first, then from parts
                    # Check both 'name' and 'target_name' fields
                    name = return_val.get('name') or return_val.get('target_name') or extract_name_from_parts(parts, intent)
                    return_val['failure_reason'] = get_failure_reason(intent, name)
                    modified_count += 1
    
    # Write back
    if modified_count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"  Modified {modified_count} return objects (out of {total_false} with success=false)")
    else:
        print(f"  No modifications needed ({total_false} false returns already had failure_reason)")
    
    return modified_count, total_false


def main():
    random.seed(42)  # For reproducibility
    
    script_dir = Path(__file__).parent
    
    # Find all JSONC files
    jsonc_files = list(script_dir.glob('*.jsonc'))
    print(f"Found {len(jsonc_files)} JSONC files\n")
    
    total_modified = 0
    total_false_returns = 0
    
    for filepath in sorted(jsonc_files):
        modified, false_count = process_file(filepath)
        total_modified += modified
        total_false_returns += false_count
    
    print(f"\n{'='*50}")
    print(f"SUMMARY:")
    print(f"  Total files processed: {len(jsonc_files)}")
    print(f"  Total false returns found: {total_false_returns}")
    print(f"  Total modifications made: {total_modified}")


if __name__ == '__main__':
    main()
