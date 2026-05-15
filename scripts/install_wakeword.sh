#!/usr/bin/env bash
set -euo pipefail

# openwakeword 0.4.0 ships its pretrained .onnx models bundled with the
# package — no separate download needed. This script just verifies they're
# accessible.

uv run python - <<'PY'
import openwakeword
paths = openwakeword.get_pretrained_model_paths()
if not paths:
    raise SystemExit("No bundled wake-word models found. Reinstall openwakeword.")
print(f"openWakeWord bundles {len(paths)} pretrained wake words:")
for p in paths:
    print(f"  - {p}")
PY
