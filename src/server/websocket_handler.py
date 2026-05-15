import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import websockets

from src.classifier.classifier_protocol import ClassifierProtocol
from src.config import EMIT_VOICESTRING, HOST, LATENCY_WARNING_MS, PORT
from src.responder import dispatch
from src.telemetry.cache import TelemetryCache

logger = logging.getLogger(__name__)


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def log_info(message: str) -> None:
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {message}")


def log_success(message: str) -> None:
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")


def log_warning(message: str) -> None:
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {message}")


def log_error(message: str) -> None:
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}")


def log_response(message: str) -> None:
    print(f"{Colors.HEADER}[RESPONSE]{Colors.ENDC} {Colors.HEADER}{message}{Colors.ENDC}")


async def handle_message(
    message_text: str,
    classifier: ClassifierProtocol,
    cache: TelemetryCache,
    sio_client,
) -> str:
    start_time = time.time()
    request_id = "unknown"
    try:
        message = json.loads(message_text)
        command = message.get("command", "")
        request_id = message.get("request_id", "unknown")

        if not command:
            log_warning("Empty command received")
            return json.dumps({
                "status": "error",
                "error_message": "No command provided",
                "request_id": request_id,
            })

        log_info(f"Classifying command: '{command}'")
        classification = classifier.classify(command)

        response_text = dispatch.respond(command, classification, cache)
        log_response(response_text)

        latency_ms = round((time.time() - start_time) * 1000, 2)
        if latency_ms > LATENCY_WARNING_MS:
            log_warning(f"High latency: {latency_ms}ms (threshold: {LATENCY_WARNING_MS}ms)")

        if classification["confidence"] < 0.65 or classification["intent"] not in dispatch.REGISTRY:
            log_warning(
                f"miss: text={command!r} intent={classification['intent']} "
                f"confidence={classification['confidence']:.3f}"
            )

        response = {
            "status": "success",
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "response_text": response_text,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for opt in ("all_intents", "parameters", "matched_keywords"):
            if opt in classification:
                response[opt] = classification[opt]

        log_success(
            f"Intent: {classification['intent']}, Confidence: {classification['confidence']:.3f}, "
            f"Latency: {latency_ms}ms"
        )

        if EMIT_VOICESTRING and sio_client is not None:
            await sio_client.emit("voiceString", response_text)

        return json.dumps(response)

    except json.JSONDecodeError as exc:
        log_error(f"Invalid JSON received: {exc}")
        return json.dumps({
            "status": "error",
            "error_message": "Invalid JSON",
            "request_id": request_id,
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing message")
        return json.dumps({
            "status": "error",
            "error_message": "Server error",
            "request_id": request_id,
        })


def _make_client_handler(classifier, cache, sio_client):
    async def handle_client(websocket):
        client_address = websocket.remote_address
        log_success(f"Client connected: {client_address}")
        try:
            async for message in websocket:
                log_info(f"Received from {client_address}: {message[:100]}...")
                response = await handle_message(message, classifier, cache, sio_client)
                await websocket.send(response)
                log_info(f"Response sent to {client_address}")
        except websockets.exceptions.ConnectionClosed:
            log_warning(f"Client disconnected: {client_address}")
        except Exception as exc:  # noqa: BLE001
            log_error(f"Error handling client {client_address}: {exc}")
        finally:
            log_info(f"Connection closed: {client_address}")

    return handle_client


async def start_websocket(classifier, cache, sio_client) -> None:
    log_info("Starting CORVUS WebSocket Server...")
    log_info(f"Host: {HOST}")
    log_info(f"Port: {PORT}")

    async with websockets.serve(_make_client_handler(classifier, cache, sio_client), HOST, PORT):
        log_success(f"Server running on ws://{HOST}:{PORT}")
        log_info("Waiting for Unity connection...")
        log_info("Press Ctrl+C to stop the server")
        await asyncio.Future()
