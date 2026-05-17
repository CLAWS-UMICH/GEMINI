from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import socketio


def new_state(config_path: str | Path | None = None) -> dict:
    path = Path(config_path or Path(__file__).with_name("config.json"))
    config = json.loads(path.read_text(encoding="utf-8"))
    return {
        "metrics": config["metrics"],
        "forecast_alert_stages_sec": sorted(float(value) for value in config.get("forecast_alert_stages_sec", [])),
        "history": defaultdict(deque),
        "sent_forecast_stages": set(),
        "path_eta_sec": None,
    }


# -----------------------------
# Alert checks
# -----------------------------
def process_packet(state: dict, packet: dict) -> list[dict]:
    telemetry = packet.get("pr_telemetry", packet)
    timestamp = _parse_timestamp(telemetry, packet)
    alerts = []

    for metric, spec in state["metrics"].items():
        if metric not in telemetry:
            continue

        try:
            value = float(telemetry[metric])
        except (TypeError, ValueError):
            continue
        path_eta_sec = state["path_eta_sec"]
        threshold_result = evaluate_threshold(metric, value, spec)
        if threshold_result is not None:
            severity, breach, threshold = threshold_result
            alerts.append(make_alert(severity, metric, value, breach, threshold, timestamp, spec))
        if not spec.get("forecast", False):
            continue

        history = state["history"][metric]
        history.append((timestamp, value))
        while len(history) > int(spec["history_limit"]):
            history.popleft()

        if len(history) < 2:
            continue

        slope = best_fit_slope(list(history))
        if slope == 0.0:
            continue

        forecast_candidates = []
        for breach, key in (("LOW", "critical_low"), ("HIGH", "critical_high")):
            if key in spec:
                eta_sec = (float(spec[key]) - value) / slope
                if eta_sec >= 0:
                    forecast_candidates.append((eta_sec, breach, float(spec[key])))
        if not forecast_candidates:
            continue

        eta_sec, breach, threshold = min(forecast_candidates)
        stage_sec = next((stage for stage in state["forecast_alert_stages_sec"] if eta_sec <= stage), None)
        stage_key = (metric, breach, stage_sec)
        if stage_sec is None or stage_key in state["sent_forecast_stages"]:
            continue
        state["sent_forecast_stages"].add(stage_key)

        if path_eta_sec is not None and eta_sec <= path_eta_sec:
            severity = "CRITICAL_PATH"
        else:
            severity = "PREDICTIVE"
        alerts.append(make_forecast_alert(severity, metric, value, breach, threshold, eta_sec, timestamp, path_eta_sec, spec, stage_sec))

    return alerts


def evaluate_threshold(metric: str, value: float, spec: dict) -> tuple[str, str, float] | None:
    warning_low = _number_or_none(spec.get("warning_low", spec.get("min")))
    warning_high = _number_or_none(spec.get("warning_high", spec.get("max")))
    caution_low = _number_or_none(spec.get("caution_low"))
    caution_high = _number_or_none(spec.get("caution_high"))

    if warning_low is not None and value <= warning_low:
        return "WARNING", "LOW", warning_low
    if warning_high is not None and value >= warning_high:
        return "WARNING", "HIGH", warning_high
    if caution_low is not None and value <= caution_low:
        return "CAUTION", "LOW", caution_low
    if caution_high is not None and value >= caution_high:
        return "CAUTION", "HIGH", caution_high
    return None


def _number_or_none(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_timestamp(telemetry: dict, packet: dict) -> float:
    raw = telemetry.get("rover_elapsed_time", packet.get("mission_elapsed_time"))
    if raw is None:
        return time.monotonic()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return time.monotonic()


def best_fit_slope(points: list[tuple[float, float]]) -> float:
    n = len(points)
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    return 0.0 if denom == 0.0 else (n * sxy - sx * sy) / denom


def make_alert(severity: str, metric: str, value: float, breach: str, threshold: float, timestamp: float, spec: dict, eta_sec: float | None = None, eta_status: str = "UNKNOWN") -> dict:
    alert = {
        "severity": severity,
        "metric": metric,
        "value": value,
        "breach": breach,
        "threshold": threshold,
        "unit": spec.get("unit", ""),
        "timestamp": timestamp,
    }
    if eta_sec is not None:
        alert["eta_sec"] = eta_sec
        alert["eta_status"] = eta_status
    return alert


def make_forecast_alert(severity: str, metric: str, value: float, breach: str, threshold: float, eta_sec: float, timestamp: float, path_eta_sec: float | None, spec: dict, stage_sec: float | None = None) -> dict:
    return {
        "severity": severity,
        "metric": metric,
        "value": value,
        "breach": breach,
        "threshold": threshold,
        "eta_sec": eta_sec,
        "forecast_stage_sec": stage_sec,
        "path_eta_sec": path_eta_sec,
        "unit": spec.get("unit", ""),
        "timestamp": timestamp,
    }


# -----------------------------
# Socket listener
# -----------------------------
def start(connection: dict, on_alert, config_path: str | Path | None = None):
    state = new_state(config_path)
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_socket_listener,
        args=(connection["backend_url"], state, on_alert, stop_event),
        name="alerts",
        daemon=True,
    )
    thread.start()

    return SimpleNamespace(
        stop=stop_event.set,
        update_path_eta=lambda eta_sec: state.__setitem__("path_eta_sec", eta_sec),
    )


def run_socket_listener(backend_url: str, state: dict, on_alert, stop_event: threading.Event) -> None:
    sio = socketio.Client(reconnection=True)

    @sio.on("rover-telemetry")
    def on_rover_telemetry(packet) -> None:
        for alert in process_packet(state, packet):
            on_alert(alert)

    sio.connect(backend_url, wait=True)
    stop_event.wait()
    sio.disconnect()
