import asyncio
import websockets
import json
import time
from datetime import datetime, timezone

# Import our modules
from src.config import (
      HOST, PORT, INTENT_MAPPINGS, LATENCY_WARNING_MS,
      USE_ONNX_MODEL, ONNX_MODEL_PATH, LABELS_PATH,
      USE_NN_MODEL, NN_MODEL_PATH, TRAINING_DATA_PATH
)
from src.classifier.ai_model import IntentClassifier, DistilBertClassifier
from src.classifier.intent_classifier import IntentClassifier as NNClassifier
from src.classifier.routing_classifier import RoutingClassifier

class Colors:
      HEADER = '\033[95m'
      OKBLUE = '\033[94m'
      OKGREEN = '\033[92m'
      WARNING = '\033[93m'
      FAIL = '\033[91m'
      ENDC = '\033[0m'
      BOLD = '\033[1m'

def log_info(message):
    """Info message in blue"""
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {message}")

def log_success(message):
    """Log success message in green."""
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")

def log_warning(message):
    """Log warning message in yellow."""
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {message}")

def log_error(message):
    """Log error message in red."""
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}")

router = RoutingClassifier()

if USE_NN_MODEL:
    with open(TRAINING_DATA_PATH) as f:
        _data = json.load(f)
    _labels = [intent["label"] for intent in _data["intents"]]
    nn_classifier = NNClassifier(_labels, NN_MODEL_PATH)

def handle_message(message_text: str, classifier) -> str:
    """Process a message from Unity and return a response"""

    start_time = time.time()

    try:
        # Step 1: Parse incoming JSON
        message = json.loads(message_text)
        log_info(f"Received message: {message}")

        # Step 2: Extract required fields
        command = message.get("command", "")
        request_id = message.get("request_id", "unknown")

        # Validate command exists
        if not command:
                log_warning("Empty command received")
                return json.dumps({
                    "status": "error",
                    "error_message": "No command provided",
                    "request_id": request_id
                })
        
        # Step 3: Classify the intent
        log_info(f"Classifying command: '{command}'")
        classification = classifier.classify(command)
        routing = router.route(command, classification)

        # Step 4: Calculate latency
        end_time = time.time()
        latency_ms = round((end_time - start_time) * 1000, 2)

        # Step 5: Check if latency is too high
        if latency_ms > LATENCY_WARNING_MS:
            log_warning(f"High latency: {latency_ms}ms (threshold: {LATENCY_WARNING_MS}ms)")

        # Step 6: Build response
        response = {
            "status": "success",
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "route": routing["route"],
            "reason": routing["reason"],
            "request_id": request_id,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if "all_intents" in classification:
            response["all_intents"] = classification["all_intents"]
        if "parameters" in classification:
            response["parameters"] = classification["parameters"]
        if "matched_keywords" in classification:
            response["matched_keywords"] = classification["matched_keywords"]

        # Log the result
        log_success(f"Intent: {classification['intent']}, Confidence: {classification['confidence']}, Latency: {latency_ms}ms")

        return json.dumps(response)
    except json.JSONDecodeError as e:
        # Handle invalid JSON
        log_error(f"Invalid JSON received: {e}")
        return json.dumps({
             "status": "error",
             "error_message": f"Invalid JSON format: {str(e)}",
             "request_id": "unknown"
        })
    except Exception as e:
        # Handle any other errors
        log_error(f"Error processing message: {e}")
        return json.dumps({
             "status": "error",
             "error_message": f"Server error: {str(e)}",
             "request_id": message.get("request_id", "unknown") if 'message' in locals() else "unknown"
        })

async def handle_client(websocket):
    """Handle a connected WebSocket client"""

    # Get client address for logging
    client_address = websocket.remote_address
    log_success(f"Client connected: {client_address}")

    # Create classifier instance for this client
    # Each client gets their own classifier (thread-safe)
    if USE_NN_MODEL:
        classifier = nn_classifier
    elif USE_ONNX_MODEL:
        classifier = DistilBertClassifier(ONNX_MODEL_PATH, LABELS_PATH)
        log_info("Using ONNX model for classification")
    else:
        classifier = IntentClassifier(INTENT_MAPPINGS)
        log_info("Using keyword matching for clasification")

    try:
        async for message in websocket:
            log_info(f"Received from {client_address}: {message[:100]}...")

            response = handle_message(message, classifier)

            await websocket.send(response)
            log_info(f"Response sent to {client_address}")
    except websockets.exceptions.ConnectionClosed:
        log_warning(f"Client disconnected: {client_address}")
    except Exception as e:
        log_error(f"Error handling client {client_address}: {e}")
    finally:
        log_info(f"Connection closed: {client_address}")

async def start_websocket():
    """Start the WebSocket server."""
    log_info(f"Starting CORVUS WebSocket Server...")
    log_info(f"Host: {HOST}")
    log_info(f"Port: {PORT}")
    log_info(f"Intent mappings loaded: {len(INTENT_MAPPINGS)} intents")
    if USE_ONNX_MODEL:
        log_info(f"ONNX Model Loaded")

    async with websockets.serve(handle_client, HOST, PORT):
        log_success(f"Server running on ws://{HOST}:{PORT}")
        log_info("Waiting for Unity connection...")
        log_info("Press Ctrl+C to stop the server")
        await asyncio.Future()