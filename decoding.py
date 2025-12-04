from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

Prediction = Tuple[str, str]

TASK_NAME_START = "TASK_NAME_START"
TASK_NAME_CONT = "TASK_NAME_CONT"


def normalize_task_predictions(predictions: Iterable[Prediction]) -> List[Prediction]:
    """Ensure task name labels always open with TASK_NAME_START.

    The classifier occasionally emits TASK_NAME_CONT tokens without first
    producing a TASK_NAME_START. This function rewrites those stray labels
    so downstream decoders never have to guess whether a token is the start
    of a task name span.
    """
    normalized: List[Prediction] = []
    inside_task_name = False

    for token, label in predictions:
        if label == TASK_NAME_START:
            inside_task_name = True
            normalized.append((token, label))
        elif label == TASK_NAME_CONT:
            if inside_task_name:
                normalized.append((token, label))
            else:
                # Treat unexpected continuations as the start of a new span.
                normalized.append((token, TASK_NAME_START))
                inside_task_name = True
        else:
            inside_task_name = False
            normalized.append((token, label))

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
    """Provide a lightweight structured view over raw token predictions."""
    normalized = normalize_task_predictions(list(predictions))
    task_names = [_tokens_to_text(span) for span in _collect_task_name_spans(normalized)]
    return {
        "get_vitals": any(label == "GET_VITALS" for _, label in normalized),
        "create_task": any(label == "CREATE_TASK" for _, label in normalized),
        "task_names": task_names,
        "tokens": normalized,
    }


__all__ = [
    "decode_predictions",
    "extract_task_names",
    "normalize_task_predictions",
]

