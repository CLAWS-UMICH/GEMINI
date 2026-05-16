"""EVA-mode response handlers.

Phase 2: all 45 EVA labels are template-driven; see
`src/core/responder/registry_eva.py`. This file is intentionally empty
of handler functions — the registry constructs them inline via
`template_handler()`. Kept as a stable import target in case a future
EVA label needs a hand-rolled handler.
"""
