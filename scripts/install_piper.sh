#!/usr/bin/env bash
set -euo pipefail

# Downloads a Piper voice (en_US-lessac-medium by default) into models/tts/piper/.

VOICE="${1:-en_US-lessac-medium}"
TARGET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models/tts/piper"
mkdir -p "$TARGET"

BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
curl -L -o "$TARGET/$VOICE.onnx" "$BASE_URL/$VOICE.onnx"
curl -L -o "$TARGET/$VOICE.onnx.json" "$BASE_URL/$VOICE.onnx.json"

echo "Installed Piper voice to: $TARGET/$VOICE.onnx"
