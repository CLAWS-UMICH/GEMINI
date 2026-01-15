"""
Simple data loader that combines all JSONC files from the singletools directory.

This module loads and parses all .jsonc files from data/singletools,
combining them into a single list of training examples at runtime.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple


def strip_jsonc_comments(content: str) -> str:
    """Remove JavaScript-style comments from JSONC content."""
    # Remove single-line comments (// ...)
    content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
    # Remove multi-line comments (/* ... */)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    return content


def load_jsonc_file(file_path: Path) -> Dict[str, Any]:
    """Load a single JSONC file, stripping comments before parsing."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip comments
    clean_content = strip_jsonc_comments(content)
    
    try:
        return json.loads(clean_content)
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse {file_path}: {e}")
        return {}


def load_all_singletools(singletools_dir: str = None) -> List[Dict[str, Any]]:
    """
    Load all JSONC files from the singletools directory and combine their data.
    
    Returns:
        List of all training examples combined from all files.
    """
    if singletools_dir is None:
        # Default path relative to this script
        singletools_dir = Path(__file__).parent / "data" / "singletools"
    else:
        singletools_dir = Path(singletools_dir)
    
    if not singletools_dir.exists():
        raise FileNotFoundError(f"Singletools directory not found: {singletools_dir}")
    
    all_data = []
    loaded_files = 0
    
    for jsonc_file in sorted(singletools_dir.glob("*.jsonc")):
        file_data = load_jsonc_file(jsonc_file)
        
        # Each file should have a "data" array with the training examples
        if "data" in file_data and isinstance(file_data["data"], list):
            all_data.extend(file_data["data"])
            loaded_files += 1
            print(f"  Loaded {len(file_data['data'])} examples from {jsonc_file.name}")
    
    print(f"Total: Loaded {len(all_data)} examples from {loaded_files} files")
    return all_data


def load_twotools_combos(twotools_dir: str = None) -> List[Dict[str, Any]]:
    """
    Load the two-tool combo training data from the twotools directory.
    
    Returns:
        List of two-tool combo training examples.
    """
    if twotools_dir is None:
        # Default path relative to this script
        twotools_dir = Path(__file__).parent / "data" / "twotools"
    else:
        twotools_dir = Path(twotools_dir)
    
    combo_file = twotools_dir / "intentcombos.jsonc"
    
    if not combo_file.exists():
        print(f"Two-tool combos file not found: {combo_file}")
        return []
    
    file_data = load_jsonc_file(combo_file)
    
    if "data" in file_data and isinstance(file_data["data"], list):
        print(f"  Loaded {len(file_data['data'])} two-tool combo examples from {combo_file.name}")
        return file_data["data"]
    
    return []


def load_all_training_data(singletools_dir: str = None, twotools_dir: str = None) -> List[Dict[str, Any]]:
    """
    Load all training data from both singletools and twotools directories.
    
    Returns:
        Combined list of all training examples.
    """
    all_data = []
    
    # Load single-tool examples
    print("Loading single-tool data...")
    single_data = load_all_singletools(singletools_dir)
    all_data.extend(single_data)
    
    # Load two-tool combo examples
    print("\nLoading two-tool combo data...")
    combo_data = load_twotools_combos(twotools_dir)
    all_data.extend(combo_data)
    
    print(f"\nCombined total: {len(all_data)} training examples")
    return all_data


def discover_labels(data: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """
    Discover all unique tool_calls and token types from the data.
    
    Returns:
        Tuple of (tool_labels, token_labels)
    """
    tool_labels: Set[str] = set()
    token_labels: Set[str] = set()
    
    for item in data:
        # Collect tool calls
        for tool in item.get("tool_calls", []):
            tool_labels.add(tool)
        
        # Collect token types from parts
        for part in item.get("parts", []):
            token_labels.add(part["type"])
    
    # Sort for consistency
    return sorted(tool_labels), sorted(token_labels)


def get_data_and_labels(singletools_dir: str = None, twotools_dir: str = None, include_combos: bool = True) -> Tuple[List[Dict], List[str], List[str]]:
    """
    Convenience function to load data and discover labels in one call.
    
    Args:
        singletools_dir: Optional path to single-tool data directory
        twotools_dir: Optional path to two-tool combo data directory
        include_combos: If True, include two-tool combo examples (default True)
    
    Returns:
        Tuple of (data, tool_labels, token_labels)
    """
    if include_combos:
        data = load_all_training_data(singletools_dir, twotools_dir)
    else:
        print("Loading singletools data only...")
        data = load_all_singletools(singletools_dir)
    
    tool_labels, token_labels = discover_labels(data)
    
    print(f"\nDiscovered {len(tool_labels)} tool labels: {tool_labels}")
    print(f"Discovered {len(token_labels)} token labels: {token_labels}")
    
    return data, tool_labels, token_labels


if __name__ == "__main__":
    # Test the loader
    data, tool_labels, token_labels = get_data_and_labels()
    
    print(f"\n--- Summary ---")
    print(f"Total examples: {len(data)}")
    print(f"Tool labels: {tool_labels}")
    print(f"Token labels: {token_labels}")
    
    # Show a sample
    if data:
        print(f"\nSample example:")
        print(json.dumps(data[0], indent=2))
