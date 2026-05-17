from __future__ import annotations

from types import SimpleNamespace
import threading


# -----------------------------
# AIA listener placeholder
# -----------------------------
def recommend_procedure(alert: dict) -> dict:
    metric = alert["metric"]
    severity = alert["severity"]
    breach = alert["breach"].lower()
    return {
        "severity": severity,
        "metric": metric,
        "explanation": f"{metric} is {breach} and triggered a {severity} alert.",
        "recommended_action": "Review the relevant procedure and stabilize the affected system.",
        "source_procedure_id": None,
    }


def start(connection: dict):
    stop_event = threading.Event()
    thread = threading.Thread(target=stop_event.wait, name="aia", daemon=True)
    thread.start()
    return SimpleNamespace(stop=stop_event.set)
