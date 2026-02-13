import asyncio
from src.server.websocket_handler import start_websocket, log_info, log_error

async def start_server():
    """Start all server connections"""
    log_info("Starting CORVUS Server...")

    # Start WebSocket 
    await start_websocket()
    # TODO add Socket.IO

def main():
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        log_info("\nServer stopped by user (Ctrl+C)")
    except Exception as e:
        log_error(f"Server crashed: {e}")
        raise

if __name__ == "__main__":
    main()