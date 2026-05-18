from __future__ import annotations

import socketio


# Fixed world-coordinate origin for the full map grid.
# matrix[0][0] (top-left cell) represents world coordinate (-6550, -9750).
#   X range: -6550 to -5450  (matrix columns, left -> right)
#   Y range: -10450 to -9750 (matrix rows,    top  -> bottom)
MAP_TOPLEFT_X = -6550
MAP_TOPLEFT_Y = -9750


# -----------------------------
# Backend socket
# -----------------------------
def connect(backend_url: str):
    """Connect to the TTTDTT backend Socket.IO server and return the client."""
    sio = socketio.Client(reconnection=True)
    sio.connect(backend_url, wait=True)
    return sio


def send_alert(sio, alert: dict) -> None:
    """Emit a metric-warning event to the backend.

    Per SOCKETIO_CLIENTS.md the event is "metric-warning" and the payload
    is the alert object (or list of objects).
    """
    sio.emit("metric-warning", alert)


def send_matrix(sio, matrix_payload: dict | list) -> None:
    """Emit an occupancy matrix update to the backend.

    Per SOCKETIO_CLIENTS.md the event is "matrix-update" and the payload
    must be shaped as:
        {"data": [[int, ...], ...], "topleft": {"x": float, "y": float}}

    The topleft is always the fixed map origin: x=-6550, y=-9750.

    If the caller passes a raw 2-D list (legacy usage), it is wrapped with
    the correct map origin. If the caller passes a structured dict it is
    forwarded as-is (rover_control.send_occupancy_matrix already embeds the
    correct topleft).
    """
    if isinstance(matrix_payload, list):
        # Legacy path: caller supplied only the 2-D grid without metadata.
        payload = {
            "data": matrix_payload,
            "topleft": {"x": MAP_TOPLEFT_X, "y": MAP_TOPLEFT_Y},
        }
    else:
        # Preferred path: caller supplied the full structured dict (from
        # rover_control.send_occupancy_matrix which already sets the correct
        # MAP_TOPLEFT_X / MAP_TOPLEFT_Y values).
        payload = matrix_payload

    sio.emit("matrix-update", payload)