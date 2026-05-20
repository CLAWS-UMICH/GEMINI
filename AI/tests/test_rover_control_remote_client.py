from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


CONTROLFILES_DIR = Path(__file__).resolve().parents[1] / "controlfiles"
if str(CONTROLFILES_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLFILES_DIR))


class FakeSocketClient:
    def __init__(self, *args, **kwargs):
        self.connected = False
        self.handlers = {}

    def event(self, func):
        self.handlers[func.__name__] = func
        return func

    def on(self, event_name):
        def decorator(func):
            self.handlers[event_name] = func
            return func

        return decorator

    def connect(self, *args, **kwargs):
        self.connected = True
        if "connect" in self.handlers:
            self.handlers["connect"]()

    def disconnect(self):
        self.connected = False

    def emit(self, *args, **kwargs):
        event_name = args[0]
        if event_name == "rover-throttle":
            self.handlers["rover-throttle-result"]({"success": True})
        return None


def import_rover_control():
    sys.modules.pop("rover_control", None)
    sys.modules["socketio"] = types.SimpleNamespace(Client=FakeSocketClient)
    return importlib.import_module("rover_control")


class RemoteRoverClientFreshnessTest(unittest.TestCase):
    def test_returns_fresh_cached_telemetry(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")
        now = 100.0

        with patch.object(rover_control.time, "monotonic", return_value=now):
            client.sio.handlers["rover-telemetry"]({"pr_telemetry": {"speed": 1}})
            payload = client.get_json_for_command(rover_control.GET_ROVER_JSON)

        self.assertEqual(payload, {"pr_telemetry": {"speed": 1}})

    def test_stale_cached_telemetry_times_out_waiting_for_fresh_event(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        with patch.object(rover_control.time, "monotonic", return_value=0.0):
            client.sio.handlers["rover-telemetry"]({"pr_telemetry": {"speed": 1}})

        with patch.object(rover_control.time, "monotonic", return_value=10.0):
            with self.assertRaisesRegex(RuntimeError, "fresh remote rover telemetry"):
                client.get_json_for_command(rover_control.GET_ROVER_JSON, timeout_seconds=0.0)

    def test_new_event_after_stale_cache_is_returned(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        with patch.object(rover_control.time, "monotonic", return_value=0.0):
            client.sio.handlers["rover-telemetry"]({"pr_telemetry": {"speed": 1}})

        with patch.object(rover_control.time, "monotonic", return_value=10.0):
            client.sio.handlers["rover-telemetry"]({"pr_telemetry": {"speed": 2}})
            payload = client.get_json_for_command(rover_control.GET_ROVER_JSON, timeout_seconds=0.0)

        self.assertEqual(payload, {"pr_telemetry": {"speed": 2}})

    def test_remote_command_waits_for_backend_success_result(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        self.assertTrue(client.emit("rover-throttle", 20.0))

    def test_matrix_emit_does_not_wait_for_command_result(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        self.assertTrue(client.emit("matrix", [[0, 1], [2, 3]]))

    def test_remote_command_returns_false_for_backend_failure_result(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        def failed_emit(event_name, payload=None):
            client.sio.handlers[f"{event_name}-result"]({"success": False})

        client.sio.emit = failed_emit

        self.assertFalse(client.emit("rover-throttle", 20.0))

    def test_remote_command_raises_for_backend_error(self):
        rover_control = import_rover_control()
        client = rover_control.RemoteRoverClient("http://backend")

        def error_emit(event_name, payload=None):
            client.sio.handlers["udp-command-error"]({"command": event_name, "error": "UDP timeout"})

        client.sio.emit = error_emit

        with self.assertRaisesRegex(RuntimeError, "UDP timeout"):
            client.emit("rover-throttle", 20.0)


if __name__ == "__main__":
    unittest.main()
