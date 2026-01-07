import json
from collections import Counter, defaultdict

# Load the prompts
with open('data.json', 'r', encoding='utf-8') as f:
    prompts = json.load(f)

# Count different metrics
type_counts = Counter()
prompt_counts = defaultdict(lambda: {'total': 0, 'types': Counter()})
tool_call_counts = Counter()  # NEW: count prompt-level tool calls

# Analyze each prompt
for i, prompt_entry in enumerate(prompts):
    # Check for required fields
    if 'prompt' not in prompt_entry:
        print(f"WARNING: Entry {i} missing 'prompt' field")
        continue
    if 'parts' not in prompt_entry:
        print(f"WARNING: Entry {i} missing 'parts' field")
        continue

    prompt_text = prompt_entry['prompt']
    parts = prompt_entry['parts']

    # NEW: Count tool calls at prompt level
    tool_calls = prompt_entry.get('tool_calls', [])
    for tool_call in tool_calls:
        tool_call_counts[tool_call] += 1

    # Count types in each part (token level)
    for part in parts:
        if 'type' not in part:
            print(f"WARNING: Entry {i} has part missing 'type' field")
            continue
        part_type = part['type']
        type_counts[part_type] += 1

        # Track which prompts contain which types
        prompt_counts[part_type]['total'] += 1

# Print analysis
print("=" * 70)
print("PROMPT TYPE DISTRIBUTION ANALYSIS (NEW ARCHITECTURE)")
print("=" * 70)
print(f"\nTotal prompts: {len(prompts)}")
print(f"Total parts: {sum(type_counts.values())}")
print("\nNEW ARCHITECTURE:")
print("  - Prompt level: tool_calls field indicates which tools are invoked")
print("  - Token level: TEXT, TASK_NAME_START, TASK_NAME_CONT only")
print()

# Sort by count (descending)
sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

print("PART TYPE COUNTS:")
print("-" * 70)
for part_type, count in sorted_types:
    percentage = (count / sum(type_counts.values())) * 100
    print(f"{part_type:25s}: {count:5d} ({percentage:5.2f}%)")

print("\n" + "=" * 70)
print("\nPROMPTS CONTAINING EACH TYPE:")
print("-" * 70)
sorted_prompt_types = sorted(prompt_counts.items(), key=lambda x: x[1]['total'], reverse=True)
for part_type, data in sorted_prompt_types:
    percentage = (data['total'] / len(prompts)) * 100
    print(f"{part_type:25s}: {data['total']:5d} prompts ({percentage:5.2f}%)")

# Calculate balance recommendations
print("\n" + "=" * 70)
print("BALANCE RECOMMENDATIONS:")
print("-" * 70)

# Determine which functional types need more examples
functional_types = [t for t in type_counts.keys() if t != 'JUSTTEXT']
if functional_types:
    avg_functional = sum(type_counts[t] for t in functional_types) / len(functional_types)
    print(f"\nAverage count per functional type: {avg_functional:.1f}")
    print(f"\nTypes that need more examples (below average):")

    underrepresented = []
    for part_type in functional_types:
        count = type_counts[part_type]
        if count < avg_functional * 0.8:  # 20% below average
            deficit = int(avg_functional - count)
            underrepresented.append((part_type, count, deficit))
            print(f"  {part_type:25s}: {count:5d} (needs ~{deficit} more)")

    print(f"\nTypes that are well-represented (at or above average):")
    for part_type in functional_types:
        count = type_counts[part_type]
        if count >= avg_functional * 0.8:
            print(f"  {part_type:25s}: {count:5d}")

# NEW: Tool call analysis (prompt-level classification)
print("\n" + "=" * 70)
print("PROMPT-LEVEL TOOL CALL DISTRIBUTION:")
print("-" * 70)
if tool_call_counts:
    sorted_tools = sorted(tool_call_counts.items(), key=lambda x: x[1], reverse=True)
    total_tool_calls = sum(tool_call_counts.values())
    for tool, count in sorted_tools:
        pct = (count / len(prompts)) * 100
        print(f"{tool:25s}: {count:5d} prompts ({pct:5.2f}%)")

    # Balance recommendation for tools
    print("\nTOOL BALANCE:")
    avg_tool_count = total_tool_calls / len(tool_call_counts) if tool_call_counts else 0
    print(f"Average count per tool: {avg_tool_count:.1f}")
    for tool, count in sorted_tools:
        if count < avg_tool_count * 0.8:
            deficit = int(avg_tool_count - count)
            print(f"  {tool:25s}: needs ~{deficit} more prompts")
else:
    print("No tool calls found in data")

print("\n" + "=" * 70)
