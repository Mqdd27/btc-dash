import pytest

from apps.ml.dataset import ALL_FEATURE_COLUMNS, build_ml_dataset, load_split
from apps.ml.models import ModelVersion
from apps.ml.prediction import get_active_model_version, load_model, predict_win_probability
from apps.ml.training import train_model

from .test_dataset import seed_ml_data, strategy_config, symbol  # noqa: F401


@pytest.mark.django_db
def test_predict_win_probability_matches_raw_model_output(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)
    build_ml_dataset(strategy_config, symbol, "1h", splits=splits)
    model_version = train_model(strategy_config, symbol, "1h", name="test_model")
    test_df = load_split(strategy_config, symbol, "1h", "test")

    proba = predict_win_probability(model_version, test_df)
    raw_model = load_model(model_version)
    expected = raw_model.predict_proba(test_df[ALL_FEATURE_COLUMNS])[:, 1]

    assert (proba.to_numpy() == expected).all()
    assert ((proba >= 0) & (proba <= 1)).all()


@pytest.mark.django_db
def test_get_active_model_version_only_returns_active(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)
    build_ml_dataset(strategy_config, symbol, "1h", splits=splits)
    model_version = train_model(strategy_config, symbol, "1h", name="test_model")

    assert get_active_model_version(strategy_config, symbol, "1h") is None

    model_version.active = True
    model_version.save(update_fields=["active"])

    assert get_active_model_version(strategy_config, symbol, "1h") == model_version
