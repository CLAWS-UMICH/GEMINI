from __future__ import annotations

import socketio


# -----------------------------
# Backend socket
# -----------------------------
def connect(backend_url: str):
    sio = socketio.Client(reconnection=True)
    sio.connect(backend_url, wait=True)
    return sio


def send_alert(sio, alert: dict) -> None:
    sio.emit("metric-warning", alert)


def send_matrix(sio, matrix: list[list[int]]) -> None:
    sio.emit("matrix", matrix)
