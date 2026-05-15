from typing import Protocol, TypedDict


class Classification(TypedDict, total=False):
    intent: str
    confidence: float
    all_intents: list
    parameters: dict
    matched_keywords: list


class ClassifierProtocol(Protocol):
    def classify(self, command: str) -> Classification: ...
