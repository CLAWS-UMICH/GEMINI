import json

import pytest

from src.core.classifier.factory import build_classifier


def test_factory_returns_nn_when_multilabel_sidecars_missing(tmp_path, monkeypatch):
    """With no models/multilabel/label2id.json present, factory falls back to NNClassifier."""
    fake_models = tmp_path / "models"
    fake_models.mkdir()
    (fake_models / "multilabel").mkdir()
    # No label2id.json inside → fallback path
    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory.NN_MODEL_PATH", tmp_path / "nonexistent_nn.pt")
    monkeypatch.setattr("src.core.classifier.factory.TRAINING_DATA_PATH",
                        tmp_path / "training_data.json")

    (tmp_path / "training_data.json").write_text('{"intents": [{"label": "x"}]}')

    clf = build_classifier(mode="eva")
    assert clf.__class__.__name__ == "NNClassifier"


def test_factory_returns_multilabel_when_sidecars_present(tmp_path, monkeypatch):
    """When label2id.json is present, factory builds a MultilabelClassifier."""
    import torch
    from src.core.classifier.multilabel_classifier import MultilabelClassifier

    fake_models = tmp_path / "models"
    (fake_models / "multilabel").mkdir(parents=True)
    catalogs = fake_models / "intent_catalogs"
    catalogs.mkdir()

    labels = {"get_heart_rate_eva1": 0, "Get_battery_level": 1}
    (fake_models / "multilabel" / "label2id.json").write_text(json.dumps(labels))
    (catalogs / "intenteva.json").write_text(json.dumps(
        [{"intent": "get_heart_rate_eva1", "description": ""}]
    ))
    (catalogs / "intentPR.json").write_text(json.dumps(
        [{"intent": "Get_battery_level", "description": ""}]
    ))

    class StubModule:
        def forward_texts(self, texts, device):
            return torch.zeros(len(texts), len(labels))

    def _stub_build(multilabel_dir, mode):
        return MultilabelClassifier(
            multilabel_dir,
            mode=mode,
            catalogs_dir=catalogs,
            module=StubModule(),
        )

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory._build_multilabel", _stub_build)

    clf = build_classifier(mode="eva")
    assert clf.__class__.__name__ == "MultilabelClassifier"
