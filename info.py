import json
from pathlib import Path
from collections import Counter

data_path = Path("data.json")
with data_path.open("r", encoding="utf-8") as handle:
    data = json.load(handle)

print(f"Total examples: {len(data)}")

# Count tool calls
tool_call_counts = Counter()
for example in data:
    for tool_call in example["tool_calls"]:
        tool_call_counts[tool_call] += 1

print("\nTool Call Distribution:")
total_tool_calls = sum(tool_call_counts.values())
for tool_call, count in tool_call_counts.most_common():
    percentage = (count / total_tool_calls) * 100
    print(f"  {tool_call}: {count} ({percentage:.1f}%)")

# Count part types
part_type_counts = Counter()
total_parts = 0
for example in data:
    for part in example["parts"]:
        part_type_counts[part["type"]] += 1
        total_parts += 1

print(f"\nTotal parts: {total_parts}")
print("Part Type Distribution:")
for part_type, count in part_type_counts.most_common():
    percentage = (count / total_parts) * 100
    print(f"  {part_type}: {count} ({percentage:.1f}%)")

# Count examples by number of tool calls
tool_call_length_counts = Counter()
for example in data:
    num_tools = len(example["tool_calls"])
    tool_call_length_counts[num_tools] += 1

print("\nExamples by Number of Tool Calls:")
for num_tools in sorted(tool_call_length_counts.keys()):
    count = tool_call_length_counts[num_tools]
    percentage = (count / len(data)) * 100
    print(f"  {num_tools} tool(s): {count} examples ({percentage:.1f}%)")

# Count examples by number of parts
part_length_counts = Counter()
for example in data:
    num_parts = len(example["parts"])
    part_length_counts[num_parts] += 1

print("\nExamples by Number of Parts:")
for num_parts in sorted(part_length_counts.keys()):
    count = part_length_counts[num_parts]
    percentage = (count / len(data)) * 100
    print(f"  {num_parts} part(s): {count} examples ({percentage:.1f}%)")

# Count number of tasks in CREATE_TASK examples
task_count_distribution = Counter()
create_task_examples = [ex for ex in data if "CREATE_TASK" in ex["tool_calls"]]

# Log examples with CREATE_TASK but no tasks internally
create_task_no_tasks = []

for example in create_task_examples:
    # Count TASK_NAME_START parts to determine number of tasks
    task_count = sum(1 for part in example["parts"] if part["type"] == "TASK_NAME_START")
    task_count_distribution[task_count] += 1
    
    # Log examples with CREATE_TASK but no TASK_NAME_START parts
    if task_count == 0:
        create_task_no_tasks.append(example)

print(f"\nCREATE_TASK Examples: {len(create_task_examples)}")
print("Number of Tasks per CREATE_TASK Example:")
for num_tasks in sorted(task_count_distribution.keys()):
    count = task_count_distribution[num_tasks]
    percentage = (count / len(create_task_examples)) * 100
    print(f"  {num_tasks} task(s): {count} examples ({percentage:.1f}%)")

# Log CREATE_TASK examples with no tasks
if create_task_no_tasks:
    print(f"\nCREATE_TASK examples with no tasks internally ({len(create_task_no_tasks)}):")
    for i, example in enumerate(create_task_no_tasks, 1):
        print(f"  {i}. \"{example['prompt']}\"")
        print(f"     Tool calls: {example['tool_calls']}")
        print(f"     Parts: {[part['type'] for part in example['parts']]}")
        print()
else:
    print("\nNo CREATE_TASK examples found with zero tasks internally.")