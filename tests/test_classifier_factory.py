import json

import pytest

from src.core.classifier.factory import build_classifier


class _FakeClassifier:
    def __init__(self, name):
        self.name = name

    def classify(self, command):
        return {"intent": self.name, "confidence": 1.0}


def _stub_nn_paths(tmp_path, monkeypatch):
    """Point NN paths at a stub training file so NNClassifier construction succeeds."""
    monkeypatch.setattr("src.core.classifier.factory.NN_MODEL_PATH", tmp_path / "nonexistent_nn.pt")
    monkeypatch.setattr("src.core.classifier.factory.TRAINING_DATA_PATH",
                        tmp_path / "training_data.json")
    (tmp_path / "training_data.json").write_text('{"intents": [{"label": "x"}]}')


def test_factory_returns_multiintent_for_eva_when_best_model_bundle_present(tmp_path, monkeypatch):
    """EVA mode uses the EVA-Model multi-intent bundle when present."""
    fake_models = tmp_path / "models"
    best_model = fake_models / "EVA-Model"
    best_model.mkdir(parents=True)
    for name in [
        "multiintent.pt",
        "label2id.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
    ]:
        (best_model / name).write_text("{}")

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory.BEST_MODEL_DIR", best_model)

    def _stub_build_multiintent(model_dir):
        assert model_dir == best_model
        return _FakeClassifier("multiintent")
    monkeypatch.setattr("src.core.classifier.factory._build_multiintent", _stub_build_multiintent)

    clf = build_classifier(mode="eva")
    assert clf.name == "multiintent"


def test_factory_returns_nn_for_eva_when_best_model_bundle_missing(tmp_path, monkeypatch):
    """EVA mode falls back to NNClassifier when models/EVA-Model is incomplete."""
    fake_models = tmp_path / "models"
    (fake_models / "EVA-Model").mkdir(parents=True)

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory.BEST_MODEL_DIR", fake_models / "EVA-Model")
    monkeypatch.setattr(
        "src.core.classifier.factory._build_nn",
        lambda: _FakeClassifier("nn"),
    )

    def _fail_build_multiintent(model_dir):
        raise AssertionError("incomplete EVA-Model bundle must not build MultiIntentClassifier")
    monkeypatch.setattr("src.core.classifier.factory._build_multiintent", _fail_build_multiintent)

    clf = build_classifier(mode="eva")
    assert clf.name == "nn"


def test_factory_returns_nn_for_pr_when_multilabel_sidecars_missing(tmp_path, monkeypatch):
    """PR mode falls back to NNClassifier when models/PR-Model/label2id.json is missing."""
    fake_models = tmp_path / "models"
    fake_models.mkdir()
    (fake_models / "PR-Model").mkdir()

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr(
        "src.core.classifier.factory._build_nn",
        lambda: _FakeClassifier("nn"),
    )

    clf = build_classifier(mode="pr")
    assert clf.name == "nn"


def test_factory_returns_multilabel_for_pr_when_sidecars_present(tmp_path, monkeypatch):
    """PR mode builds a MultilabelClassifier when label2id.json is present."""
    fake_models = tmp_path / "models"
    (fake_models / "PR-Model").mkdir(parents=True)

    labels = {"get_heart_rate_eva1": 0, "Get_battery_level": 1}
    (fake_models / "PR-Model" / "label2id.json").write_text(json.dumps(labels))

    def _stub_build(multilabel_dir, mode):
        assert mode == "pr"
        assert multilabel_dir == fake_models / "PR-Model"
        return _FakeClassifier("PR-Model")

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory._build_multilabel", _stub_build)

    clf = build_classifier(mode="pr")
    assert clf.name == "PR-Model"


def test_factory_pr_ignores_best_model_bundle(tmp_path, monkeypatch):
    """PR mode should not select the EVA-Model bundle."""
    fake_models = tmp_path / "models"
    best_model = fake_models / "EVA-Model"
    best_model.mkdir(parents=True)
    (best_model / "multiintent.pt").write_text("")
    (best_model / "label2id.json").write_text(json.dumps({"vitals_heart_rate": 0}))
    (fake_models / "PR-Model").mkdir(parents=True)

    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)
    monkeypatch.setattr("src.core.classifier.factory.BEST_MODEL_DIR", best_model)
    monkeypatch.setattr(
        "src.core.classifier.factory._build_nn",
        lambda: _FakeClassifier("nn"),
    )

    def _fail_build_multiintent(model_dir):
        raise AssertionError("PR mode must ignore models/EVA-Model")
    monkeypatch.setattr("src.core.classifier.factory._build_multiintent", _fail_build_multiintent)

    clf = build_classifier(mode="pr")
    assert clf.name == "nn"
