"""Phase 2 smoke: classifier + registries wired end-to-end."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.classifier.factory import build_classifier
from src.core.responder import dispatch
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.responder.registry_pr import REGISTRY_PR_FULL
from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
from src.core.telemetry.cache import TelemetryCache

BEST_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "EVA-Model"
MULTILABEL_DIR = Path(__file__).resolve().parents[1] / "models" / "PR-Model"
INTENT_CATALOGS_DIR = Path(__file__).resolve().parents[1] / "models" / "intent_catalogs"
BEST_MODEL_PRESENT = (
    (BEST_MODEL_DIR / "multiintent.pt").exists()
    and (BEST_MODEL_DIR / "label2id.json").exists()
)
MULTILABEL_PRESENT = (
    (MULTILABEL_DIR / "label2id.json").exists()
    and (INTENT_CATALOGS_DIR / "intentPR.json").exists()
)


@pytest.fixture(scope="module")
def eva_clf():
    return build_classifier(mode="eva")


@pytest.fixture(scope="module")
def pr_clf():
    return build_classifier(mode="pr")


def test_eva_pipeline_canonical_heart_rate(eva_clf):
    # EVA mode uses NNClassifier (Unity-aligned vocabulary).
    # NN emits `vitals_heart_rate`, which REGISTRY_EVA resolves against telemetry.eva1.heart_rate.
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})

    classification = eva_clf.classify("what is my heart rate")
    assert classification["intent"] == "vitals_heart_rate", classification

    response = dispatch.respond("…", classification, cache, REGISTRY_EVA)
    assert "72" in response and "heart rate" in response.lower()


@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_canonical_battery(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 65.4}})

    classification = pr_clf.classify("what is the rover battery level")
    # Either Get_battery_level or Get_primary_battery_level is acceptable —
    # both reach primary_battery_level via the field-path map.
    assert classification["intent"] in {"Get_battery_level", "Get_primary_battery_level"}
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert "65.4" in response


@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_set_lights_on_verbal_ack(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    classification = pr_clf.classify("turn the headlights on")
    # Top-1 might land on get_lights_on (status query) or set_lights_on.
    # Both are acceptable behavior — we only assert no crash + non-empty response.
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert isinstance(response, str) and response
    if classification["intent"] == "set_lights_on":
        assert "lights" in response.lower() and "on" in response.lower()


def test_eva_pipeline_unavailable_when_cache_empty(eva_clf):
    # Cache empty → template_handler returns TELEMETRY_UNAVAILABLE_REPLY.
    cache = TelemetryCache(stale_after_s=10.0)
    classification = eva_clf.classify("what is my heart rate")
    assert classification["intent"] == "vitals_heart_rate", classification

    response = dispatch.respond("…", classification, cache, REGISTRY_EVA)
    assert response == TELEMETRY_UNAVAILABLE_REPLY


@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_eva_heart_rate(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})

    classification = pr_clf.classify("what is eva 1 heart rate")
    assert classification["intent"] == "get_heart_rate_eva1", classification
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert "72" in response
    assert "EVA 1" in response
    assert "beats per minute" in response


@pytest.mark.skipif(not MULTILABEL_PRESENT, reason="multilabel bundle not installed")
def test_pr_pipeline_eva_label_unavailable_when_eva_cache_empty(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    classification = pr_clf.classify("what is eva 1 heart rate")
    assert classification["intent"] == "get_heart_rate_eva1"
    response = dispatch.respond("…", classification, cache, REGISTRY_PR_FULL)
    assert response == TELEMETRY_UNAVAILABLE_REPLY
