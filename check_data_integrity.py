import json
import os
from pathlib import Path

def check_file_logging(filepath, log_file):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()
    json_lines = [line for line in lines if not line.strip().startswith('//')]
    json_content = '\n'.join(json_lines)
    
    try:
        data = json.loads(json_content)
        if isinstance(data, dict) and 'data' in data:
            items = data['data']
        elif isinstance(data, list):
            items = data
        else:
            log_file.write(f"Skipping {filepath.name}: Unknown format\n")
            return

        mismatches = []
        for idx, item in enumerate(items):
            prompt = item.get('prompt', '')
            parts = item.get('parts', [])
            
            reconstructed = ''.join([p.get('text', '') for p in parts])
            
            if prompt != reconstructed:
                mismatches.append(f"  Index {idx}: Prompt length {len(prompt)} != Parts length {len(reconstructed)}")
                mismatches.append(f"    Prompt: {prompt}")
                mismatches.append(f"    Parts:  {reconstructed}")

        if mismatches:
            log_file.write(f"File: {filepath.name}\n")
            print(f"File: {filepath.name}") # Keep printing filename to stdout
            for m in mismatches:
                log_file.write(m + "\n")
            log_file.write("-" * 40 + "\n")
            
    except Exception as e:
        log_file.write(f"Error parsing {filepath.name}: {e}\n")

def main():
    with open("integrity_log.txt", "w", encoding='utf-8') as log_file:
        base_dir = Path("c:/Users/beasl/.stuff/school/claws/25-26/GEMINI/data/twotools")
        print(f"Scanning {base_dir}...")
        log_file.write(f"Scanning {base_dir}...\n")
        
        for file in base_dir.glob("*.jsonc"):
            check_file_logging(file, log_file)

if __name__ == "__main__":
    main()
