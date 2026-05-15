"""Smoke test for the trained MiniLM + NN classifier.

Loads the model from disk and asserts a canonical command classifies to the
expected intent above the confidence threshold. Doubles as a sanity check that
the embedder and labels are in sync with the model checkpoint.

Also exposes `main()` for the `classifier-test` console script so the original
interactive REPL still works.
"""

import json

import pytest

from src.core.classifier.nn_classifier import NNClassifier
from src.config import CONFIDENCE_THRESH_HIGH, NN_MODEL_PATH, TRAINING_DATA_PATH


@pytest.fixture(scope="module")
def classifier() -> NNClassifier:
    if not NN_MODEL_PATH.exists():
        pytest.skip(f"NN checkpoint missing at {NN_MODEL_PATH}; run training first.")
    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    return NNClassifier(labels, NN_MODEL_PATH)


@pytest.mark.parametrize(
    "command,expected_intent",
    [
        ("what's my heart rate", "vitals_heart_rate"),
        ("how much battery time do I have left", "vitals_batt_time_left"),
    ],
)
def test_canonical_commands_classify_correctly(classifier, command, expected_intent):
    result = classifier.classify(command)
    assert result["intent"] == expected_intent, (
        f"Got {result['intent']!r} for {command!r} (confidence={result['confidence']:.3f})"
    )
    assert result["confidence"] >= CONFIDENCE_THRESH_HIGH


def main() -> None:
    """Interactive REPL preserved from the old `nn-test` script."""
    if not NN_MODEL_PATH.exists():
        print(f"NN checkpoint missing at {NN_MODEL_PATH}; run training first.")
        return
    with open(TRAINING_DATA_PATH) as f:
        labels = [intent["label"] for intent in json.load(f)["intents"]]
    clf = NNClassifier(labels, NN_MODEL_PATH)
    print("Ready. Type a command (or 'quit').\n")
    while True:
        command = input("> ")
        if command.lower() == "quit":
            return
        print(json.dumps(clf.classify(command), indent=2))


if __name__ == "__main__":
    main()
