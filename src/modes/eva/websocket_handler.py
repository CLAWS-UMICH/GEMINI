import asyncio
import logging

import websockets

from src.config import HOST, PORT
from src.modes.eva.protocol import serialize_final
from src.modes.eva.session import AudioReady, EvaSession

logger = logging.getLogger(__name__)


def _make_client_handler(classifier, cache, sio_client, stt, vad, registry):
    async def handle_client(websocket):
        client_address = websocket.remote_address
        logger.info("Client connected: %s", client_address)
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
                else:
                    session.on_text(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Client disconnected: %s", client_address)
        except Exception:
            logger.exception("Error handling client %s", client_address)
        finally:
            logger.info("Connection closed: %s", client_address)

    return handle_client


async def start_websocket(classifier, cache, sio_client, stt, vad, registry) -> None:
    logger.info("Starting CORVUS-EVA WebSocket Server...")
    logger.info("Host: %s", HOST)
    logger.info("Port: %s", PORT)

    handler = _make_client_handler(classifier, cache, sio_client, stt, vad, registry)
    async with websockets.serve(handler, HOST, PORT):
        logger.info("Server running on ws://%s:%s", HOST, PORT)
        logger.info("Waiting for Unity connection...")
        logger.info("Press Ctrl+C to stop the server")
        await asyncio.Future()
