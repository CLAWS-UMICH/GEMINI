from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

# CORVUS Server Configuration

# WebSocket server settings
HOST = os.getenv("WS_HOST", "0.0.0.0")
PORT = int(os.getenv("WS_PORT", "8765"))

# Confidence thresholds for intent classification
CONFIDENCE_THRESH_HIGH = 0.65       # Execute immediately

# Paths Config
BASE_DIR = Path(__file__).parent.parent

NN_MODEL_DIR = BASE_DIR / "models" / "classifier" / "minilm-nn"
MINILM_MODEL_DIR = BASE_DIR / "models" / "embeddings" / "minilm"
TRAINING_DATA_PATH = BASE_DIR / "data" / "intents" / "training_data.json"
NN_MODEL_PATH = NN_MODEL_DIR / "intent_nn.pt"

# AI inference target is <350ms, 500ms is a warning threshold
LATENCY_WARNING_MS = 500

# TTTDTT Socket.IO hub
TTTDTT_URL = os.getenv("TTTDTT_URL", "http://localhost:5001")
STALE_TELEMETRY_S = float(os.getenv("STALE_TELEMETRY_S", "10.0"))

# Whether to republish each response on TTTDTT 'voiceString' (spec §5.4)
EMIT_VOICESTRING = os.getenv("EMIT_VOICESTRING", "1") not in ("0", "false", "False")