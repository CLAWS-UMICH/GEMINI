from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

sys.modules["locate"] = SimpleNamespace(start=lambda *args, **kwargs: None)
AI_controller = importlib.import_module("AI_controller")


class FakeRunner:
    def __init__(self, name, calls, interrupt=False):
        self.name = name
        self.calls = calls
        self.interrupt = interrupt

    def join(self):
        self.calls.append((self.name, "join"))
        if self.interrupt:
            raise KeyboardInterrupt

    def stop(self):
        self.calls.append((self.name, "stop"))


def test_udp_mode_does_not_start_backend_or_alerts(monkeypatch):
    calls = []
    monkeypatch.setattr(AI_controller, "LOCATE_TRANSPORT", "udp")
    monkeypatch.setattr(AI_controller.backend_bridge, "connect", lambda url: calls.append(("connect", url)))
    monkeypatch.setattr(AI_controller.alerts, "start", lambda conn, cb: calls.append(("alerts", conn)))
    monkeypatch.setattr(
        AI_controller.locate,
        "start",
        lambda connection, on_path_update=None, on_eta_update=None: FakeRunner("locate", calls),
    )

    AI_controller.main()

    assert ("locate", "join") in calls
    assert ("locate", "stop") in calls
    assert not any(call[0] == "connect" for call in calls)
    assert not any(call[0] == "alerts" for call in calls)


def test_socket_mode_starts_backend_alerts_and_aia(monkeypatch):
    calls = []

    class FakeBackend:
        def disconnect(self):
            calls.append(("backend", "disconnect"))

    class FakeAlertRunner:
        def update_path_eta(self, eta):
            calls.append(("alert", "eta", eta))

        def stop(self):
            calls.append(("alert", "stop"))

    monkeypatch.setattr(AI_controller, "LOCATE_TRANSPORT", "socket")
    monkeypatch.setattr(AI_controller.backend_bridge, "connect", lambda url: calls.append(("connect", url)) or FakeBackend())
    monkeypatch.setattr(AI_controller.alerts, "start", lambda conn, cb: calls.append(("alerts", conn)) or FakeAlertRunner())
    monkeypatch.setattr(AI_controller.aia, "start", lambda conn: calls.append(("aia", conn)) or FakeRunner("aia", calls))
    monkeypatch.setattr(
        AI_controller.locate,
        "start",
        lambda connection, on_path_update=None, on_eta_update=None: FakeRunner("locate", calls),
    )

    AI_controller.main()

    assert ("connect", AI_controller.BACKEND_URL) in calls
    assert ("alerts", {"backend_url": AI_controller.BACKEND_URL}) in calls
    assert ("aia", {"backend_url": AI_controller.BACKEND_URL}) in calls
    assert ("locate", "stop") in calls
    assert ("alert", "stop") in calls
    assert ("aia", "stop") in calls
    assert ("backend", "disconnect") in calls


def test_socket_mode_alert_callback_sends_metric_warning(monkeypatch):
    calls = []
    captured = {}

    class FakeBackend:
        def disconnect(self):
            calls.append(("backend", "disconnect"))

    class FakeAlertRunner:
        def update_path_eta(self, eta):
            pass

        def stop(self):
            calls.append(("alert", "stop"))

    def fake_alerts_start(conn, callback):
        captured["alert_callback"] = callback
        return FakeAlertRunner()

    monkeypatch.setattr(AI_controller, "LOCATE_TRANSPORT", "socket")
    monkeypatch.setattr(AI_controller.backend_bridge, "connect", lambda url: FakeBackend())
    monkeypatch.setattr(AI_controller.backend_bridge, "send_alert", lambda backend, alert: calls.append(("send_alert", alert)))
    monkeypatch.setattr(
        AI_controller.aia,
        "recommend_procedure",
        lambda alert: calls.append(("recommend_procedure", alert)) or {"recommended_action": "Slow down."},
    )
    monkeypatch.setattr(AI_controller.alerts, "start", fake_alerts_start)
    monkeypatch.setattr(AI_controller.aia, "start", lambda conn: FakeRunner("aia", calls))
    monkeypatch.setattr(
        AI_controller.locate,
        "start",
        lambda connection, on_path_update=None, on_eta_update=None: FakeRunner("locate", calls),
    )

    AI_controller.main()
    alert = {"severity": "WARNING", "metric": "speed"}
    captured["alert_callback"](alert)

    assert ("recommend_procedure", alert) in calls
    assert ("send_alert", {**alert, "procedure": {"recommended_action": "Slow down."}}) in calls


def test_keyboard_interrupt_still_cleans_up_socket_mode(monkeypatch):
    calls = []

    class FakeBackend:
        def disconnect(self):
            calls.append(("backend", "disconnect"))

    class FakeAlertRunner:
        def update_path_eta(self, eta):
            pass

        def stop(self):
            calls.append(("alert", "stop"))

    monkeypatch.setattr(AI_controller, "LOCATE_TRANSPORT", "socket")
    monkeypatch.setattr(AI_controller.backend_bridge, "connect", lambda url: FakeBackend())
    monkeypatch.setattr(AI_controller.alerts, "start", lambda conn, cb: FakeAlertRunner())
    monkeypatch.setattr(AI_controller.aia, "start", lambda conn: FakeRunner("aia", calls))
    monkeypatch.setattr(
        AI_controller.locate,
        "start",
        lambda connection, on_path_update=None, on_eta_update=None: FakeRunner("locate", calls, interrupt=True),
    )

    AI_controller.main()

    assert ("locate", "stop") in calls
    assert ("alert", "stop") in calls
    assert ("aia", "stop") in calls
    assert ("backend", "disconnect") in calls
