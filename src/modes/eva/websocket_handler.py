import asyncio
import logging

import websockets

from src.config import HOST, PORT
from src.modes.eva.protocol import serialize_final
from src.modes.eva.session import AudioReady, EvaSession

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


def _make_client_handler(classifier, cache, sio_client, stt, vad, registry):
    async def handle_client(websocket):
        client_address = websocket.remote_address
        log_success(f"Client connected: {client_address}")
        session = EvaSession(
            vad=vad,
            stt=stt,
            classifier=classifier,
            cache=cache,
            sio_client=sio_client,
            registry=registry,
        )
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    ready = session.on_binary(message)
                    if isinstance(ready, AudioReady):
                        final = await session.finalize(ready)
                        await websocket.send(serialize_final(final))
                        log_response(final.response)
                else:
                    session.on_text(message)
        except websockets.exceptions.ConnectionClosed:
            log_warning(f"Client disconnected: {client_address}")
        except Exception as exc:  # noqa: BLE001
            log_error(f"Error handling client {client_address}: {exc}")
            logger.exception("client handler crashed")
        finally:
            log_info(f"Connection closed: {client_address}")

    return handle_client


async def start_websocket(classifier, cache, sio_client, stt, vad, registry) -> None:
    log_info("Starting CORVUS-EVA WebSocket Server...")
    log_info(f"Host: {HOST}")
    log_info(f"Port: {PORT}")

    handler = _make_client_handler(classifier, cache, sio_client, stt, vad, registry)
    async with websockets.serve(handler, HOST, PORT):
        log_success(f"Server running on ws://{HOST}:{PORT}")
        log_info("Waiting for Unity connection...")
        log_info("Press Ctrl+C to stop the server")
        await asyncio.Future()
