
import json
import re
from pathlib import Path
from simpledatacombine import strip_jsonc_comments

def check_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    clean_content = strip_jsonc_comments(content)
    try:
        data = json.loads(clean_content)
    except json.JSONDecodeError as e:
        print(f"Error parsing {file_path}: {e}")
        return

    if not isinstance(data, dict) or "data" not in data:
        return

    items = data["data"]
    for i, item in enumerate(items):
        prompt = item.get("prompt", "")
        parts = item.get("parts", [])
        
        parts_text = "".join(p["text"] for p in parts)
        
        if len(prompt) != len(parts_text):
            print(f"Mismatch in {file_path.name} at index {i}")
            print(f"  Prompt ({len(prompt)}): {prompt!r}")
            print(f"  Parts  ({len(parts_text)}): {parts_text!r}")
            print("-" * 40)
        elif prompt != parts_text:
             print(f"Content mismatch in {file_path.name} at index {i}")
             print(f"  Prompt: {prompt!r}")
             print(f"  Parts : {parts_text!r}")
             print("-" * 40)

def main():
    base_dir = Path("data")
    singletools_dir = base_dir / "singletools"
    twotools_dir = base_dir / "twotools"
    
    print("Checking singletools...")
    if singletools_dir.exists():
        for f in sorted(singletools_dir.glob("*.jsonc")):
            check_file(f)
            
    print("\nChecking twotools...")
    if twotools_dir.exists():
        for f in sorted(twotools_dir.glob("*AND*.jsonc")):
            check_file(f)

if __name__ == "__main__":
    main()
