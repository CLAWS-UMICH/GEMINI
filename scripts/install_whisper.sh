#!/usr/bin/env bash
set -euo pipefail

# Downloads the faster-whisper medium.en checkpoint to models/stt/whisper-medium.en/.
# faster-whisper auto-downloads on first model construction, but doing it here
# means demos don't pause on first launch.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$PROJECT_ROOT/models/stt/whisper-medium.en"

# Refuse to run from WSL when the project's .venv looks Windows-shaped —
# `uv run` would recreate the venv with Linux binaries and clobber the
# Windows install. Run this from Windows (PowerShell) in that case.
if grep -qi microsoft /proc/version 2>/dev/null && [[ -d "$PROJECT_ROOT/.venv/Scripts" ]]; then
    echo "ERROR: project .venv looks Windows-shaped (./.venv/Scripts exists) but this" >&2
    echo "       script is being run from WSL. \`uv run\` would recreate the venv as" >&2
    echo "       Linux and wipe the Windows install. Run from Windows PowerShell." >&2
    exit 2
fi

mkdir -p "$MODEL_DIR"

uv run python - <<PY
from faster_whisper import download_model
path = download_model("medium.en", output_dir="$MODEL_DIR")
print(f"Whisper medium.en downloaded to: {path}")
PY
