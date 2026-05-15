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

    # Stub the training data path with a minimal valid JSON
    (tmp_path / "training_data.json").write_text('{"intents": [{"label": "x"}]}')

    clf = build_classifier(mode="eva")
    assert clf.__class__.__name__ == "NNClassifier"


def test_factory_raises_for_multilabel_until_implemented(tmp_path, monkeypatch):
    """When sidecars exist, factory tries to build MultilabelClassifier. Phase 1 stubs that
    with NotImplementedError so phase-2 implementation is forced."""
    fake_models = tmp_path / "models"
    (fake_models / "multilabel").mkdir(parents=True)
    (fake_models / "multilabel" / "label2id.json").write_text('{"foo": 0}')
    monkeypatch.setattr("src.core.classifier.factory.MODELS_DIR", fake_models)

    with pytest.raises(NotImplementedError, match="multi-label"):
        build_classifier(mode="eva")
