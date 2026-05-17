import json

import pytest

from src.core.classifier.factory import build_classifier


def _stub_nn_paths(tmp_path, monkeypatch):
    """Point NN paths at a stub training file so NNClassifier construction succeeds."""
    monkeypatch.setattr("src.core.classifier.factory.NN_MODEL_PATH", tmp_path / "nonexistent_nn.pt")
    monkeypatch.setattr("src.core.classifier.factory.TRAINING_DATA_PATH",
                        tmp_path / "training_data.json")
    (tmp_path / "training_data.json").write_text('{"intents": [{"label": "x"}]}')


def test_factory_returns_nn_for_eva_even_when_multilabel_sidecars_present(tmp_path, monkeypatch):
    """EVA mode always uses NNClassifier (Unity-aligned vocabulary); never multilabel."""
    fake_models = tmp_path / "models"
    (fake_models / "multilabel").mkdir(parents=True)
    (fake_models / "multilabel" / "label2id.json").write_text(json.dumps({"x": 0}))

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    _stub_nn_paths(tmp_path, monkeypatch)

    def _fail_build(multilabel_dir, mode):
        raise AssertionError("EVA mode must not invoke the multilabel builder")
    monkeypatch.setattr("src.core.classifier.factory._build_multilabel", _fail_build)

    clf = build_classifier(mode="eva")
    assert clf.__class__.__name__ == "NNClassifier"


def test_factory_returns_nn_for_pr_when_multilabel_sidecars_missing(tmp_path, monkeypatch):
    """PR mode falls back to NNClassifier when models/multilabel/label2id.json is missing."""
    fake_models = tmp_path / "models"
    fake_models.mkdir()
    (fake_models / "multilabel").mkdir()

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    _stub_nn_paths(tmp_path, monkeypatch)

    clf = build_classifier(mode="pr")
    assert clf.__class__.__name__ == "NNClassifier"


def test_factory_returns_multilabel_for_pr_when_sidecars_present(tmp_path, monkeypatch):
    """PR mode builds a MultilabelClassifier when label2id.json is present."""
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

    clf = build_classifier(mode="pr")
    assert clf.__class__.__name__ == "MultilabelClassifier"
