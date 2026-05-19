#!/usr/bin/env bash
set -euo pipefail

# Verifies the wake-word preprocessor + custom keyword ONNX files are present
# in the repo at the paths src/voice/wake_word.py expects.
#
# These are tracked in git (small files), so a fresh `uv sync` already has
# them — this script just confirms nothing was stripped (e.g., by Windows
# Defender, which has done it before to .onnx files inside .venv).

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REQUIRED=(
    "$PROJECT_ROOT/models/openwakeword/melspectrogram.onnx"
    "$PROJECT_ROOT/models/openwakeword/embedding_model.onnx"
    "$PROJECT_ROOT/models/wake_word/hey_corvus.onnx"
    "$PROJECT_ROOT/models/wake_word/hey_corvus.onnx.data"
)

missing=0
for path in "${REQUIRED[@]}"; do
    if [[ -f "$path" ]]; then
        echo "  ok: $path"
    else
        echo "  MISSING: $path" >&2
        missing=$((missing + 1))
    fi
done

if [[ $missing -gt 0 ]]; then
    echo "ERROR: $missing wake-word file(s) missing. Restore from git:" >&2
    echo "       git checkout HEAD -- models/openwakeword/ models/wake_word/" >&2
    exit 1
fi

echo "All wake-word files present."
