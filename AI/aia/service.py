from __future__ import annotations

from types import SimpleNamespace
import threading


# -----------------------------
# AIA listener placeholder
# -----------------------------
def start(connection: dict):
    stop_event = threading.Event()
    thread = threading.Thread(target=stop_event.wait, name="aia", daemon=True)
    thread.start()
    return SimpleNamespace(stop=stop_event.set)
