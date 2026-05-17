from __future__ import annotations

import backend_bridge


class FakeSocket:
    def __init__(self):
        self.emitted = []

    def emit(self, event, payload):
        self.emitted.append((event, payload))


def test_send_alert_emits_metric_warning_payload_unchanged():
    sio = FakeSocket()
    alert = {
        "severity": "WARNING",
        "metric": "speed",
        "value": 25,
        "threshold": 18,
        "breach": "HIGH",
        "unit": "m/s",
        "timestamp": 100.0,
    }

    backend_bridge.send_alert(sio, alert)

    assert sio.emitted == [("metric-warning", alert)]
