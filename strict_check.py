#!/usr/bin/env python3
import os
import json
import re

def strip_json_comments(text):
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text

def get_combined_text_from_parts(parts):
    return ''.join(p.get('text', '') for p in parts)

def check_entry(entry, filename, index):
    mismatches = []
    
    # Check for direct 'parts' schema
    if 'prompt' in entry and 'parts' in entry:
        prompt = entry['prompt']
        combined = get_combined_text_from_parts(entry['parts'])
        # STRICT COMPARISON NO STRIP
        if prompt != combined:
            mismatches.append(f"STRICT MISMATCH in {filename} #[{index}]:\n  P (len={len(prompt)}): '{prompt}'\n  C (len={len(combined)}): '{combined}'")
            # Highlight difference
            for i in range(min(len(prompt), len(combined))):
                if prompt[i] != combined[i]:
                    mismatches.append(f"  First diff at char {i}: '{prompt[i]}' vs '{combined[i]}'")
                    break
            if len(prompt) != len(combined):
                 mismatches.append(f"  Length diff: {len(prompt)} vs {len(combined)}")

    # Check for 'contents' schema (Gemini format)
    if 'contents' in entry:
        for content in entry['contents']:
            if content.get('role') == 'user' and 'parts' in content:
                prompt_val = entry.get('prompt', '')
                combined = get_combined_text_from_parts(content['parts'])
                if prompt_val and prompt_val != combined:
                     mismatches.append(f"STRICT MISMATCH (Contents) in {filename} #[{index}]")
    
    return mismatches

def main():
    base_dirs = ['data/twotools', 'data/singletools']
    total_mismatches = 0
    
    for d in base_dirs:
        if not os.path.exists(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith('.jsonc'):
                path = os.path.join(d, f)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        raw = file.read()
                    json_str = strip_json_comments(raw)
                    data = json.loads(json_str)
                    
                    if isinstance(data, dict):
                        for key in ['examples', 'data', 'items']:
                            if key in data and isinstance(data[key], list):
                                data = data[key]
                                break

                    if not isinstance(data, list):
                        continue

                    for i, entry in enumerate(data):
                        issues = check_entry(entry, f, i)
                        for issue in issues:
                            print(issue)
                            print("-" * 40)
                            total_mismatches += 1
                            
                except Exception as e:
                    print(f"Error processing {path}: {e}")

    print(f"\nTotal Strict Mismatches Found: {total_mismatches}")

if __name__ == '__main__':
    main()
