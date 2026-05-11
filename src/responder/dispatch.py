from src.config import CONFIDENCE_THRESH_HIGH
from src.responder.fallback import LOW_CONFIDENCE_REPLY, UNKNOWN_INTENT_REPLY
from src.responder.registry import REGISTRY


def respond(command: str, classification: dict, cache) -> str:
    if classification["confidence"] < CONFIDENCE_THRESH_HIGH:
        return LOW_CONFIDENCE_REPLY
    handler = REGISTRY.get(classification["intent"])
    if handler is None:
        return UNKNOWN_INTENT_REPLY
    return handler(command, cache, classification)
