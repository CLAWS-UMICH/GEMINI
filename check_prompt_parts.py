#!/usr/bin/env python3
"""Check for mismatches between prompt and parts in jsonc files."""

import os
import json
import re

def strip_json_comments(text):
    """Remove C-style comments from JSON text."""
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text

def get_combined_text(parts):
    """Combine all text parts into a single string."""
    texts = []
    for part in parts:
        if 'text' in part:
            texts.append(part['text'])
    return ''.join(texts)

def check_file(filepath):
    """Check a single file for mismatches."""
    mismatches = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    cleaned = strip_json_comments(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}")
        return mismatches, 0
    
    total_entries = 0
    for entry in data:
        if 'prompt' in entry and 'contents' in entry:
            prompt = entry['prompt']
            for content_item in entry['contents']:
                if content_item.get('role') == 'user' and 'parts' in content_item:
                    combined = get_combined_text(content_item['parts'])
                    if prompt.strip() != combined.strip():
                        total_entries += 1
                        mismatches.append({
                            'prompt': prompt,
                            'combined': combined,
                            'entry_index': data.index(entry)
                        })
    
    return mismatches, len(data)

def main():
    twotools_dir = 'data/twotools'
    files_with_issues = []
    
    for filename in sorted(os.listdir(twotools_dir)):
        if filename.endswith('.jsonc'):
            filepath = os.path.join(twotools_dir, filename)
            mismatches, total = check_file(filepath)
            if mismatches:
                files_with_issues.append((filename, len(mismatches), total))
                print(f"\n{filename}: {len(mismatches)} mismatches out of {total} entries")
                for i, m in enumerate(mismatches[:3]):  # Show first 3
                    print(f"  Entry {m['entry_index']}:")
                    print(f"    Prompt:   {m['prompt'][:80]}...")
                    print(f"    Combined: {m['combined'][:80]}...")
    
    print(f"\n\n=== SUMMARY ===")
    print(f"Total files with issues: {len(files_with_issues)}")
    for f, count, total in files_with_issues:
        print(f"  {f}: {count}/{total} mismatches")

if __name__ == '__main__':
    main()
