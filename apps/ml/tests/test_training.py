from pathlib import Path

import pytest
from django.conf import settings

from apps.ml.dataset import build_ml_dataset
from apps.ml.models import ModelVersion
from apps.ml.training import train_model

from .test_dataset import seed_ml_data, strategy_config, symbol  # noqa: F401


@pytest.mark.django_db
def test_train_model_creates_versioned_model_with_metrics(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)
    build_ml_dataset(strategy_config, symbol, "1h", splits=splits)

    model_version = train_model(strategy_config, symbol, "1h", name="test_model")

    assert model_version.pk is not None
    assert model_version.algorithm == "xgboost"
    assert model_version.active is False  # safety default
    assert (Path(settings.MEDIA_ROOT) / model_version.model_file).exists()
    val = model_version.validation_metrics["validation"]
    assert 0 <= val["accuracy"] <= 1
    assert "confusion_matrix" in val


@pytest.mark.django_db
def test_train_model_requires_datasets_to_exist_first(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    with pytest.raises(FileNotFoundError):
        train_model(strategy_config, symbol, "1h", name="no_dataset_yet")
