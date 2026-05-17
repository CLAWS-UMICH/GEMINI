from __future__ import annotations

import alerts.service as service
from conftest import alert_for, nested_packet


def test_alert_service_imports():
    state = service.new_state()
    assert "metrics" in state


def test_config_defines_warning_thresholds_for_all_metrics():
    state = service.new_state()
    for metric, spec in state["metrics"].items():
        has_low = "warning_low" in spec or "min" in spec
        has_high = "warning_high" in spec or "max" in spec
        assert has_low or has_high, metric
        assert "unit" in spec


def test_nominal_telemetry_returns_no_alerts():
    state = service.new_state()

    alerts = service.process_packet(state, nested_packet())

    assert alerts == []


def test_warning_alert_payload_for_high_speed():
    state = service.new_state()
    alerts = service.process_packet(state, nested_packet(speed=25))

    alert = alert_for(alerts, "speed")
    assert alert["severity"] == "WARNING"
    assert alert["metric"] == "speed"
    assert alert["value"] == 25
    assert alert["breach"] == "HIGH"
    assert alert["threshold"] == 18
    assert alert["unit"] == "m/s"
    assert alert["timestamp"] == 100.0


def test_caution_alert_payload_for_configured_caution_range(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
        {
          "metrics": {
            "speed": {
              "caution_high": 15,
              "warning_high": 18,
              "unit": "m/s"
            }
          }
        }
        """,
        encoding="utf-8",
    )
    state = service.new_state(config_path)

    alerts = service.process_packet(state, {"speed": 16, "rover_elapsed_time": 5})

    alert = alert_for(alerts, "speed")
    assert alert["severity"] == "CAUTION"
    assert alert["breach"] == "HIGH"
    assert alert["threshold"] == 15


def test_missing_metric_is_ignored():
    state = service.new_state()
    packet = nested_packet()
    del packet["pr_telemetry"]["speed"]

    alerts = service.process_packet(state, packet)

    assert all(alert["metric"] != "speed" for alert in alerts)


def test_malformed_metric_value_is_ignored_and_other_metrics_still_process():
    state = service.new_state()
    packet = nested_packet(speed="not-a-number", heart_rate=200)

    alerts = service.process_packet(state, packet)

    assert all(alert["metric"] != "speed" for alert in alerts)
    heart_rate_alert = alert_for(alerts, "heart_rate")
    assert heart_rate_alert["severity"] == "WARNING"


def test_unknown_eta_does_not_suppress_warning_alert():
    state = service.new_state()
    state["path_eta_sec"] = None

    alerts = service.process_packet(state, nested_packet(speed=25))

    alert = alert_for(alerts, "speed")
    assert alert["severity"] == "WARNING"
    assert "eta_sec" not in alert or alert["eta_sec"] is None


def test_eta_context_is_optional_and_does_not_change_severity():
    state = service.new_state()
    state["path_eta_sec"] = 120.0

    alerts = service.process_packet(state, nested_packet(speed=25))

    alert = alert_for(alerts, "speed")
    assert alert["severity"] == "WARNING"
    if "eta_sec" in alert:
        assert alert["eta_sec"] == 120.0
        assert alert["eta_status"] in {"UNKNOWN", "UNVALIDATED", "VALIDATED"}
