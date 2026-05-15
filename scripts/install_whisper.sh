#!/usr/bin/env bash
set -euo pipefail

# Downloads the faster-whisper base.en checkpoint to models/stt/whisper-base.en/.
# faster-whisper auto-downloads on first model construction, but doing it here
# means demos don't pause on first launch.

MODEL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models/stt/whisper-base.en"
mkdir -p "$MODEL_DIR"

uv run python - <<PY
from faster_whisper import download_model
path = download_model("base.en", output_dir="$MODEL_DIR")
print(f"Whisper base.en downloaded to: {path}")
PY
