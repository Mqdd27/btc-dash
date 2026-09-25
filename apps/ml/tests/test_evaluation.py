import pytest

from apps.ml.dataset import build_ml_dataset
from apps.ml.evaluation import evaluate_model
from apps.ml.training import train_model

from .test_dataset import seed_ml_data, strategy_config, symbol  # noqa: F401


@pytest.mark.django_db
def test_evaluate_model_populates_test_and_trading_comparison(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)
    build_ml_dataset(strategy_config, symbol, "1h", splits=splits)
    model_version = train_model(strategy_config, symbol, "1h", name="test_model")

    results = evaluate_model(model_version, threshold=0.65)

    assert "test" in results and "trading_comparison" in results
    comparison = results["trading_comparison"]
    assert comparison["threshold"] == 0.65
    assert "baseline" in comparison and "filtered" in comparison
    # a probability filter can only ever keep a subset of the baseline's candidates
    assert comparison["filtered"]["total_trades"] <= comparison["baseline"]["total_trades"]


@pytest.mark.django_db
def test_evaluate_model_with_threshold_zero_keeps_everything(symbol, strategy_config, settings, tmp_path):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)
    build_ml_dataset(strategy_config, symbol, "1h", splits=splits)
    model_version = train_model(strategy_config, symbol, "1h", name="test_model")

    results = evaluate_model(model_version, threshold=0.0)

    comparison = results["trading_comparison"]
    assert comparison["filtered"]["total_trades"] == comparison["baseline"]["total_trades"]
