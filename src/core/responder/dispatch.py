from src.config import CONFIDENCE_THRESH_HIGH
from src.core.responder.fallback import LOW_CONFIDENCE_REPLY, UNKNOWN_INTENT_REPLY


def respond(command: str, classification: dict, cache, registry: dict) -> str:
    if classification["confidence"] < CONFIDENCE_THRESH_HIGH:
        return LOW_CONFIDENCE_REPLY
    handler = registry.get(classification["intent"])
    if handler is None:
        return UNKNOWN_INTENT_REPLY
    return handler(command, cache, classification)
