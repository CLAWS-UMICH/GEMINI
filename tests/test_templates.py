"""Templates vendored from the teammate's intent_cli.py.

We don't import their package (torch version skew), so this test pins
the invariant: every label in label2id.json has a template, and every
template uses the `{value}` placeholder."""

import json
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


def test_every_multilabel_label_has_a_template():
    from src.core.responder.templates import INTENT_RESPONSE_TEMPLATES

    labels = set(json.loads((MODELS_DIR / "multilabel" / "label2id.json").read_text()))
    missing = labels - set(INTENT_RESPONSE_TEMPLATES)
    assert not missing, f"labels with no template: {sorted(missing)}"


def test_every_template_contains_value_placeholder():
    from src.core.responder.templates import INTENT_RESPONSE_TEMPLATES

    for label, template in INTENT_RESPONSE_TEMPLATES.items():
        assert "{value}" in template, f"{label!r}: {template!r}"


def test_template_count_matches_expected():
    """88 multilabel-era entries + 34 NN-classifier entries (22 vitals_* + 11 lowercase get_* + get_co2_scrubber)."""
    from src.core.responder.templates import INTENT_RESPONSE_TEMPLATES

    assert len(INTENT_RESPONSE_TEMPLATES) == 122
