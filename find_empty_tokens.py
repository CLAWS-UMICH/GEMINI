#!/usr/bin/env python3
import os
import json
import re

ENTITY_TYPES = {
    'WAYPOINT_NAME',
    'TASK_NAME',
    'NAVIGATION_TARGET_NAME',
    'COORDINATE_TARGET_NAME'
}

def strip_json_comments(text):
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text

def check_file(filepath):
    issues = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        data = json.loads(strip_json_comments(content))
        
        # Handle dict wrapper
        if isinstance(data, dict):
            for k in ['data', 'examples', 'items']:
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break
        
        if not isinstance(data, list):
            return issues

        for i, entry in enumerate(data):
            if 'parts' not in entry: continue
            
            parts = entry['parts']
            for j, part in enumerate(parts):
                if part.get('type') in ENTITY_TYPES:
                    text_val = part.get('text', '')
                    if text_val.strip() == "":
                        # Found empty entity
                        context_prev = parts[j-1].get('text', '') if j > 0 else "NO_PREV_TEXT"
                        prompt = entry.get('prompt', 'NO_PROMPT')
                        issues.append({
                            'file': filepath,
                            'index': i,
                            'part_index': j,
                            'type': part['type'],
                            'prompt': prompt,
                            'prev_text': context_prev
                        })

    except Exception as e:
        print(f"Error checking {filepath}: {e}")
    
    return issues

def main():
    issues = []
    for d in ['data/twotools', 'data/singletools']:
        if not os.path.exists(d): continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.jsonc'):
                path = os.path.join(d, f)
                issues.extend(check_file(path))

    print(f"Found {len(issues)} empty entity tokens.")
    for issue in issues:
        print(f"\nFile: {issue['file']} (Entry {issue['index']})")
        print(f"  Type: {issue['type']}")
        print(f"  Prompt: {issue['prompt']}")
        print(f"  Prev Text: '{issue['prev_text']}'")

if __name__ == '__main__':
    main()
