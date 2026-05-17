"""Phase 2 smoke: classifier + registries wired end-to-end.

Skipped if the multilabel bundle is not installed."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.classifier.factory import build_classifier
from src.core.responder import dispatch
from src.core.responder.registry_eva import REGISTRY_EVA
from src.core.responder.registry_pr import REGISTRY_PR
from src.core.responder.fallback import TELEMETRY_UNAVAILABLE_REPLY
from src.core.telemetry.cache import TelemetryCache

MULTILABEL_DIR = Path(__file__).resolve().parents[1] / "models" / "multilabel"
BUNDLE_PRESENT = (MULTILABEL_DIR / "label2id.json").exists()

pytestmark = pytest.mark.skipif(not BUNDLE_PRESENT, reason="multilabel bundle not installed")


@pytest.fixture(scope="module")
def eva_clf():
    return build_classifier(mode="eva")


@pytest.fixture(scope="module")
def pr_clf():
    return build_classifier(mode="pr")


def test_eva_classifier_emits_nn_vocabulary_for_heart_rate(eva_clf):
    # EVA mode now uses NNClassifier (Unity-aligned vocabulary).
    # NN emits `vitals_heart_rate`; multilabel's `get_heart_rate_eva1` is not used in EVA.
    from src.core.responder.fallback import UNKNOWN_INTENT_REPLY

    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("eva", {"telemetry": {"eva1": {"heart_rate": 72.0}, "eva2": {"heart_rate": 80.0}}})

    classification = eva_clf.classify("what is eva 1 heart rate")
    assert classification["intent"] == "vitals_heart_rate", classification

    # REGISTRY_EVA is still multilabel-keyed (Phase 2). Until it is rebuilt
    # against the NN label set, EVA responder coverage is empty → unknown-intent fallback.
    response = dispatch.respond("…", classification, cache, REGISTRY_EVA)
    assert response == UNKNOWN_INTENT_REPLY


def test_pr_pipeline_canonical_battery(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    cache.put("rover", {"pr_telemetry": {"primary_battery_level": 65.4}})

    classification = pr_clf.classify("what is the rover battery level")
    # Either Get_battery_level or Get_primary_battery_level is acceptable —
    # both reach primary_battery_level via the field-path map.
    assert classification["intent"] in {"Get_battery_level", "Get_primary_battery_level"}
    response = dispatch.respond("…", classification, cache, REGISTRY_PR)
    assert "65.4" in response


def test_pr_pipeline_set_lights_on_verbal_ack(pr_clf):
    cache = TelemetryCache(stale_after_s=10.0)
    classification = pr_clf.classify("turn the headlights on")
    # Top-1 might land on get_lights_on (status query) or set_lights_on.
    # Both are acceptable behavior — we only assert no crash + non-empty response.
    response = dispatch.respond("…", classification, cache, REGISTRY_PR)
    assert isinstance(response, str) and response
    if classification["intent"] == "set_lights_on":
        assert "lights" in response.lower() and "on" in response.lower()


def test_eva_pipeline_falls_back_when_registry_uncovered(eva_clf):
    # NN-emitted EVA intents aren't in the (still-multilabel-keyed) REGISTRY_EVA,
    # so dispatch returns UNKNOWN_INTENT_REPLY, not TELEMETRY_UNAVAILABLE_REPLY.
    # Cache contents are irrelevant — dispatch never reaches a handler.
    from src.core.responder.fallback import UNKNOWN_INTENT_REPLY

    cache = TelemetryCache(stale_after_s=10.0)
    classification = eva_clf.classify("eva 2 heart rate")
    response = dispatch.respond("…", classification, cache, REGISTRY_EVA)
    assert response == UNKNOWN_INTENT_REPLY
