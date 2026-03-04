from pathlib import Path

# CORVUS Server Configuration

# WebSocket server settings
HOST = "0.0.0.0" 
# listen on ALL network interfaces, a specific address like 127.0.0.1 
# will only allow connections from the same machine

PORT = 8765 # Port Unity will connect to

# Confidence thresholds for intent classification
CONFIDENCE_THRESH_HIGH = 0.65       # Execute immediately
CONFIDENCE_THRESH_MEDIUM = 0.5      # Execute with confirmation
# Anything below MEDIUM is considered low confidence

# Paths Config
BASE_DIR = Path(__file__).parent.parent
DB_MODEL_DIR = BASE_DIR / "models" / "classifier" / "distilbert"
ONNX_MODEL_PATH = DB_MODEL_DIR / "model.onnx"
LABELS_PATH = DB_MODEL_DIR / "labels.json"

NN_MODEL_DIR = BASE_DIR / "models" / "classifier" / "minilm-nn"
MINILM_MODEL_DIR = BASE_DIR / "models" / "embeddings" / "minilm"
TRAINING_DATA_PATH = BASE_DIR / "data" / "intents" / "training_data.json"
NN_MODEL_PATH = NN_MODEL_DIR / "intent_nn.pt"

FAISS_INDEX_DIR = BASE_DIR / "data" / "rag" / "faiss_index"
EVA_PROCEDURES_DIR = BASE_DIR / "data" / "rag" / "eva_procedures"

# Set Model Selection
USE_ONNX_MODEL = False
USE_NN_MODEL = True

# Sample intent mappings, will upgrade to AI later
INTENT_MAPPINGS = {
    # Vitals & Health
    "vitals": "check_vitals",
    "health": "check_vitals",
    "heart rate": "check_heart_rate",
    "heart": "check_heart_rate",
    "temperature": "check_temperature",
    "temp": "check_temperature",

    # Oxygen & Air Supply
    "oxygen": "check_oxygen_level",
    "o2": "check_oxygen_level",
    "air": "check_air_supply",

    # Power & Battery
    "battery": "check_battery",
    "power": "check_power_status",

    # Navigation
    "navigate": "navigate_to_waypoint",
    "airlock": "navigate_to_airlock",
    "station": "navigate_to_station",
    "waypoint": "navigate_to_waypoint",
    "go to": "navigate_to_waypoint",

    # Emergency
    "emergency": "emergency_abort",
    "abort": "emergency_abort",
    "help": "emergency_assistance",
    "alert": "emergency_alert",

    # Telemetry & Status
    "telemetry": "show_telemetry",
    "status": "show_system_status",
    "diagnostics": "run_diagnostics",
}

# AI inference target is <350ms, 500ms is a warning threshold
LATENCY_WARNING_MS = 500