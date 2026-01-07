from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

Prediction = Tuple[str, str]

TASK_NAME_START = "TASK_NAME_START"
TASK_NAME_CONT = "TASK_NAME_CONT"


def normalize_task_predictions(predictions: Iterable[Prediction]) -> List[Prediction]:
    """Ensure task name labels follow proper BIO tagging.

    Fixes common model errors:
    1. TASK_NAME_CONT without START → convert to START
    2. Two consecutive TASK_NAME_START → convert second to CONT (likely same task name)
    3. Enforces valid state transitions

    The model sometimes predicts START-START-CONT when it should predict START-CONT-CONT.
    This happens because it sees word boundaries and wants to mark each word, but
    BIO tagging requires START only for the FIRST token of an entity.
    """
    normalized: List[Prediction] = []
    inside_task_name = False
    prev_label = None

    for token, label in predictions:
        if label == TASK_NAME_START:
            if prev_label == TASK_NAME_START:
                # Two STARTs in a row is likely the model marking word boundaries
                # Convert the second START to CONT to keep them in the same span
                normalized.append((token, TASK_NAME_CONT))
                inside_task_name = True
            else:
                # Valid START - begins a new span
                inside_task_name = True
                normalized.append((token, label))
            prev_label = TASK_NAME_START
        elif label == TASK_NAME_CONT:
            if inside_task_name:
                normalized.append((token, label))
            else:
                # Orphaned CONT → treat as START
                normalized.append((token, TASK_NAME_START))
                inside_task_name = True
            prev_label = TASK_NAME_CONT
        else:
            # TEXT token ends any active span
            inside_task_name = False
            normalized.append((token, label))
            prev_label = label

    return normalized


def _collect_task_name_spans(predictions: Sequence[Prediction]) -> List[List[str]]:
    spans: List[List[str]] = []
    current: List[str] = []

    for token, label in predictions:
        if label == TASK_NAME_START:
            if current:
                spans.append(current)
            current = [token]
        elif label == TASK_NAME_CONT:
            if current:
                current.append(token)
            else:
                # Should not happen after normalization, but start a new span just in case.
                current = [token]
        else:
            if current:
                spans.append(current)
                current = []

    if current:
        spans.append(current)

    return spans


def _tokens_to_text(tokens: Sequence[str]) -> str:
    text = ""
    for token in tokens:
        if token.startswith("##"):
            text += token[2:]
        elif not text:
            text = token
        else:
            text += f" {token}"
    return text


def extract_task_names(predictions: Iterable[Prediction]) -> List[str]:
    """Return task names reconstructed from token-level predictions."""
    normalized = normalize_task_predictions(predictions)
    spans = _collect_task_name_spans(normalized)
    return [_tokens_to_text(span) for span in spans]


def decode_predictions(predictions: Iterable[Prediction]) -> dict[str, object]:
    """Provide a lightweight structured view over raw token predictions.

    Note: With the new architecture, tool calls are not predicted at token level.
    This function only extracts task names.
    """
    normalized = normalize_task_predictions(list(predictions))
    task_names = [_tokens_to_text(span) for span in _collect_task_name_spans(normalized)]
    return {
        "task_names": task_names,
        "tokens": normalized,
    }


__all__ = [
    "decode_predictions",
    "extract_task_names",
    "normalize_task_predictions",
]

