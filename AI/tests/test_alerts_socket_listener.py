from __future__ import annotations

import threading
import time

import alerts.service as service


class FakeSocketClient:
    def __init__(self, *args, **kwargs):
        self.handlers = {}
        self.connected_to = None
        self.disconnected = False

    def on(self, event):
        def decorator(func):
            self.handlers[event] = func
            return func

        return decorator

    def connect(self, backend_url, wait=True):
        self.connected_to = (backend_url, wait)

    def disconnect(self):
        self.disconnected = True


def wait_for_handler(fake, event):
    deadline = time.monotonic() + 1.0
    while event not in fake.handlers and time.monotonic() < deadline:
        time.sleep(0.001)
    assert event in fake.handlers


def test_socket_listener_processes_rover_telemetry(monkeypatch):
    fake = FakeSocketClient()
    monkeypatch.setattr(service.socketio, "Client", lambda *args, **kwargs: fake)
    state = service.new_state()
    stop_event = threading.Event()
    received = []

    thread = threading.Thread(
        target=service.run_socket_listener,
        args=("http://127.0.0.1:5001", state, received.append, stop_event),
    )
    thread.start()

    wait_for_handler(fake, "rover-telemetry")
    fake.handlers["rover-telemetry"]({"speed": 25, "rover_elapsed_time": 10})
    stop_event.set()
    thread.join(timeout=1)

    assert fake.connected_to == ("http://127.0.0.1:5001", True)
    assert fake.disconnected is True
    assert received[0]["severity"] == "WARNING"
    assert received[0]["metric"] == "speed"


def test_socket_listener_nominal_telemetry_emits_no_alert(monkeypatch):
    fake = FakeSocketClient()
    monkeypatch.setattr(service.socketio, "Client", lambda *args, **kwargs: fake)
    state = service.new_state()
    stop_event = threading.Event()
    received = []

    thread = threading.Thread(
        target=service.run_socket_listener,
        args=("http://127.0.0.1:5001", state, received.append, stop_event),
    )
    thread.start()

    wait_for_handler(fake, "rover-telemetry")
    fake.handlers["rover-telemetry"]({"speed": 5, "heart_rate": 80, "rover_elapsed_time": 10})
    stop_event.set()
    thread.join(timeout=1)

    assert received == []
    assert set(fake.handlers) == {"rover-telemetry"}
