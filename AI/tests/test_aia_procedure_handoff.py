from __future__ import annotations

import aia.service as aia_service


def test_recommend_procedure_returns_minimum_fields():
    alert = {
        "severity": "WARNING",
        "metric": "speed",
        "value": 25,
        "threshold": 18,
        "breach": "HIGH",
        "unit": "m/s",
        "timestamp": 100.0,
    }

    recommendation = aia_service.recommend_procedure(alert)

    assert recommendation["severity"] == "WARNING"
    assert recommendation["metric"] == "speed"
    assert recommendation["explanation"]
    assert recommendation["recommended_action"]
    assert "source_procedure_id" in recommendation


def test_recommend_procedure_accepts_unknown_eta_context():
    alert = {
        "severity": "CAUTION",
        "metric": "battery_level",
        "value": 35,
        "threshold": 40,
        "breach": "LOW",
        "unit": "%",
        "timestamp": 100.0,
        "eta_status": "UNKNOWN",
    }

    recommendation = aia_service.recommend_procedure(alert)

    assert recommendation["metric"] == "battery_level"
    assert recommendation["recommended_action"]
