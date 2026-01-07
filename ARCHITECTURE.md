# Multi-Task Architecture

## Overview

The model performs **TWO TASKS SIMULTANEOUSLY** using a custom multi-task architecture:

1. **Sequence Classification** (CLS token) → Predict tool calls
2. **Token Classification** → Extract task names

---

## Architecture Diagram

```
Input: "check my vitals and log a task to repair engine"
                    ↓
         [CLS] check my vitals ... [SEP]
                    ↓
        ┌───────────────────────┐
        │   DistilBERT Base     │
        │   (6 transformer      │
        │    layers, 768-dim)   │
        └───────────┬───────────┘
                    │
        ┌───────────┴──────────────────────┐
        ↓                                  ↓
┌───────────────────┐          ┌──────────────────────┐
│  CLS Token [0]    │          │  All Token Outputs   │
│   (768-dim)       │          │   (seq_len x 768)    │
└────────┬──────────┘          └──────────┬───────────┘
         ↓                                 ↓
┌────────────────────┐        ┌───────────────────────┐
│ Tool Classifier    │        │ Token Classifier      │
│  Linear(768, 3)    │        │  Linear(768, 3)       │
│                    │        │                       │
│  [GET_VITALS]      │        │  [TEXT, TEXT, ...]    │
│  [CREATE_TASK]     │        │  [START, CONT, ...]   │
│  [NAVIGATION_QUERY]│        │                       │
└────────┬───────────┘        └──────────┬────────────┘
         ↓                                ↓
    Multi-label BCE              Cross-Entropy Loss
    (sigmoid > 0.5)              (softmax argmax)
         ↓                                ↓
  ["GET_VITALS",              ["repair", "engine"]
   "CREATE_TASK"]              (task name extracted)
```

---

## Data Format

```json
{
  "prompt": "check my vitals and log a task to repair engine",
  "tool_calls": ["GET_VITALS", "CREATE_TASK"],  // Multi-label
  "parts": [
    {"type": "TEXT", "text": "check my vitals and log a task to "},
    {"type": "TASK_NAME_START", "text": "repair"},
    {"type": "TASK_NAME_CONT", "text": " engine"}
  ]
}
```

---

## Model Details

### Custom `MultiTaskModel` Class

```python
class MultiTaskModel(nn.Module):
    def __init__(self, base_model_name, num_token_labels, num_tool_labels):
        self.bert = AutoModel.from_pretrained(base_model_name)  # DistilBERT

        # Head 1: Tool classification (CLS token)
        self.tool_classifier = nn.Linear(768, 3)  # 3 tools

        # Head 2: Token classification
        self.token_classifier = nn.Linear(768, 3)  # TEXT, START, CONT
```

### Forward Pass

```python
def forward(self, input_ids, attention_mask, token_labels, tool_labels):
    # Get BERT outputs
    outputs = self.bert(input_ids, attention_mask)
    sequence_output = outputs.last_hidden_state  # (batch, seq_len, 768)

    # Task 1: Tool classification (CLS token)
    cls_output = sequence_output[:, 0, :]  # First token
    tool_logits = self.tool_classifier(cls_output)  # (batch, 3)

    # Task 2: Token classification (all tokens)
    token_logits = self.token_classifier(sequence_output)  # (batch, seq_len, 3)

    # Combined loss
    tool_loss = BCEWithLogitsLoss()(tool_logits, tool_labels)  # Multi-label
    token_loss = CrossEntropyLoss()(token_logits, token_labels)  # Multi-class
    total_loss = tool_loss + token_loss

    return {"loss": total_loss, "tool_logits": tool_logits, "token_logits": token_logits}
```

---

## Loss Functions

### 1. Tool Classification Loss (BCEWithLogitsLoss)

**Why BCE?** Tools are **multi-label** - a prompt can have multiple tools.

```python
# Ground truth (multi-hot encoding)
tool_labels = [1, 1, 0]  # GET_VITALS=1, CREATE_TASK=1, NAVIGATION_QUERY=0

# Model outputs raw logits
tool_logits = [2.3, 1.8, -0.5]  # Before sigmoid

# BCE computes loss for EACH tool independently
# L = -[y_i * log(sigmoid(x_i)) + (1-y_i) * log(1-sigmoid(x_i))]
```

**Prediction at inference:**
```python
probs = torch.sigmoid(tool_logits)  # [0.91, 0.86, 0.38]
predictions = probs > 0.5  # [1, 1, 0] → ["GET_VITALS", "CREATE_TASK"]
```

### 2. Token Classification Loss (CrossEntropyLoss)

**Why Cross-Entropy?** Each token gets **ONE** label (TEXT, START, or CONT).

```python
# Ground truth
token_labels = [0, 0, 1, 2]  # TEXT, TEXT, START, CONT

# Model outputs logits for each class
token_logits = [
    [3.2, -1.1, -0.8],  # High for TEXT (class 0)
    [2.9, -0.5, -1.2],  # High for TEXT (class 0)
    [-0.3, 4.1, 0.2],   # High for START (class 1)
    [-0.8, 0.5, 3.8],   # High for CONT (class 2)
]

# CrossEntropy computes softmax + negative log likelihood
# Prediction = argmax(softmax(logits))
```

---

## Training Process

### Data Encoding

Each example gets TWO sets of labels:

```python
{
    "input_ids": [101, 4567, 89, ...],         # Tokenized text
    "attention_mask": [1, 1, 1, ...],          # Valid tokens
    "token_labels": [0, 0, 1, 2, ...],         # Per-token labels
    "tool_labels": [1, 1, 0]                    # Multi-hot tool encoding
}
```

### Training Loop

```python
for batch in train_loader:
    outputs = model(
        input_ids=batch["input_ids"],
        attention_mask=batch["attention_mask"],
        token_labels=batch["token_labels"],
        tool_labels=batch["tool_labels"]
    )

    loss = outputs["loss"]  # Combined: tool_loss + token_loss
    loss.backward()
    optimizer.step()
```

### Evaluation Metrics

```python
# Token accuracy: % of tokens correctly classified
token_acc = correct_tokens / total_tokens

# Tool accuracy: % of examples with ALL tools correct (exact match)
tool_acc = (predicted_tools == expected_tools).all(dim=1).mean()

# Combined: Average of both
combined_acc = (token_acc + tool_acc) / 2  # Used for early stopping
```

---

## Inference Example

```python
prompt = "check vitals and log task for engine repair"

# Forward pass
outputs = model(tokenized_prompt)

# 1. Extract tools (from CLS token)
tool_probs = torch.sigmoid(outputs["tool_logits"][0])
# → [0.94, 0.89, 0.12]
tools = [TOOL_LABELS[i] for i, p in enumerate(tool_probs) if p > 0.5]
# → ["GET_VITALS", "CREATE_TASK"]

# 2. Extract task names (from token predictions)
token_preds = outputs["token_logits"].argmax(dim=-1)
# → [TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, START, CONT]
#    check vitals and log task for engine repair

task_names = extract_spans_from_predictions(token_preds)
# → ["engine repair"]
```

---

## Key Differences from Original Architecture

### ❌ OLD: Rule-Based + Single-Task Model
```
Tool detection: Regex patterns (NOT learned)
Task extraction: Model predicts tokens only
```

### ✅ NEW: Multi-Task Model
```
Tool detection: CLS token → Linear(768, 3) → Sigmoid (LEARNED)
Task extraction: All tokens → Linear(768, 3) → Softmax (LEARNED)

Both trained together with joint loss!
```

---

## Why This Works

### 1. **Shared Representations**
BERT learns representations that help BOTH tasks:
- Understanding "vitals" helps predict GET_VITALS tool
- Understanding "task for X" helps extract "X" as task name

### 2. **CLS Token Design**
BERT's CLS token is specifically designed for sequence classification:
- Aggregates information from entire sequence via self-attention
- Perfect for "what tools does this prompt invoke?"

### 3. **Multi-Task Learning Benefits**
- Tasks regularize each other (prevents overfitting)
- Shared BERT parameters are more data-efficient
- Single forward pass predicts everything (faster inference)

---

## File Structure

```
finetune.py       - Multi-task model definition + training
chat.py           - Interactive testing (loads multi-task model)
extraval.py       - Evaluation (tests both tasks)
decoding.py       - Task name extraction from token predictions
data.json         - Training data (822 examples)
extraval_data.json - Validation data (5 examples)
```

---

## Training Command

```bash
python finetune.py
```

Output:
```
Token labels: {'TASK_NAME_CONT': 0, 'TASK_NAME_START': 1, 'TEXT': 2}
Tool labels: {'GET_VITALS': 0, 'CREATE_TASK': 1, 'NAVIGATION_QUERY': 2}
Device: cpu
Starting training...

epoch=1 step=1 loss=1.2345 token_acc=0.7532 tool_acc=0.6250
epoch=1 step=2 loss=1.1234 token_acc=0.8123 tool_acc=0.7500
...
```

Model saved to: `outputs/final-model/model.pt`
