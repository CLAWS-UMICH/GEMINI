import json
from collections import Counter, defaultdict

# Load the prompts
with open('prompts.json', 'r', encoding='utf-8') as f:
    prompts = json.load(f)

# Count different metrics
type_counts = Counter()
prompt_counts = defaultdict(lambda: {'total': 0, 'types': Counter()})

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

    # Count types in each part
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
print("PROMPT TYPE DISTRIBUTION ANALYSIS")
print("=" * 70)
print(f"\nTotal prompts: {len(prompts)}")
print(f"Total parts: {sum(type_counts.values())}")
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

# Check for specific action type balance
action_types = ['GET_VITALS', 'CREATE_TASK', 'NAVIGATION_QUERY']
print("\n" + "=" * 70)
print("ACTION TYPE BALANCE:")
print("-" * 70)
for action in action_types:
    if action in type_counts:
        count = type_counts[action]
        pct = (count / sum(type_counts[a] for a in action_types if a in type_counts)) * 100
        print(f"{action:25s}: {count:5d} ({pct:5.2f}% of action types)")

print("\n" + "=" * 70)
