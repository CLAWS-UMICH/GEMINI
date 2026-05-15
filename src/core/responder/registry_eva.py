from collections.abc import Callable
from typing import Any

from src.core.responder.handlers_eva import handle_heart_rate

ResponseFn = Callable[[str, Any, dict], str]

REGISTRY_EVA: dict[str, ResponseFn] = {
    "vitals_heart_rate": handle_heart_rate,
}
