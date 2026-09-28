from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pandas as pd
import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.ml.models import ModelVersion
from apps.strategy.models import StrategyConfig
from apps.trading.engine import evaluate_now
from apps.trading.models import LiveSignal

TS = datetime(2024, 1, 1, 14, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


def seed_candle_and_snapshot(symbol, ema_20, ema_50, rsi_14, atr_14=1.0, close=100.0, ts=TS):
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts,
        open=close, high=close + 1, low=close - 1, close=close, volume=1, closed=True,
    )
    return FeatureSnapshot.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts,
        ema_20=ema_20, ema_50=ema_50, rsi_14=rsi_14, atr_14=atr_14,
    )


@pytest.mark.django_db
def test_wait_baseline_skips_inference_entirely(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=100, ema_50=100, rsi_14=50)  # no long/short setup

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"), \
         patch("apps.trading.engine.get_active_model_version") as mock_get_model:
        signal = evaluate_now(strategy_config, symbol, "1h")

    assert signal.baseline_side == "WAIT"
    assert signal.decision == "WAIT"
    assert signal.model_probability is None
    mock_get_model.assert_not_called()  # "candidate?" branch: no candidate, no inference


@pytest.mark.django_db
def test_long_baseline_without_active_model_stays_wait(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=110, ema_50=100, rsi_14=65)  # LONG setup, no model trained

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"):
        signal = evaluate_now(strategy_config, symbol, "1h")

    assert signal.baseline_side == "LONG"
    assert signal.decision == "WAIT"  # can't filter without a model -- safe default
    assert signal.model_probability is None


@pytest.mark.django_db
def test_long_baseline_with_high_probability_becomes_final_long(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=110, ema_50=100, rsi_14=65)
    model_version = ModelVersion.objects.create(
        name="test", strategy=strategy_config, symbol=symbol, timeframe="1h",
        training_start=TS, training_end=TS, features=[], hyperparameters={},
        model_file="fake.json", active=True,
    )

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"), \
         patch("apps.trading.engine.predict_win_probability", return_value=pd.Series([0.9])):
        signal = evaluate_now(strategy_config, symbol, "1h")

    assert signal.decision == "LONG"
    assert signal.model_probability == 0.9
    assert signal.model_version == model_version


@pytest.mark.django_db
def test_long_baseline_with_low_probability_is_filtered_to_wait(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=110, ema_50=100, rsi_14=65)
    ModelVersion.objects.create(
        name="test", strategy=strategy_config, symbol=symbol, timeframe="1h",
        training_start=TS, training_end=TS, features=[], hyperparameters={},
        model_file="fake.json", active=True,
    )

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"), \
         patch("apps.trading.engine.predict_win_probability", return_value=pd.Series([0.3])):
        signal = evaluate_now(strategy_config, symbol, "1h")

    assert signal.decision == "WAIT"
    assert signal.model_probability == 0.3
    assert signal.baseline_side == "LONG"  # the filter, not the baseline, changed the outcome


@pytest.mark.django_db
def test_same_candle_is_never_evaluated_twice(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=100, ema_50=100, rsi_14=50)

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"):
        first = evaluate_now(strategy_config, symbol, "1h")
        second = evaluate_now(strategy_config, symbol, "1h")

    assert first is not None
    assert second is None
    assert LiveSignal.objects.count() == 1


@pytest.mark.django_db
def test_at_evaluates_past_candle_not_latest(symbol, strategy_config):
    seed_candle_and_snapshot(symbol, ema_20=110, ema_50=100, rsi_14=65)  # 14:00, missed
    seed_candle_and_snapshot(symbol, ema_20=100, ema_50=100, rsi_14=50, ts=datetime(2024, 1, 1, 15, 0, tzinfo=dt_timezone.utc))

    with patch("apps.trading.engine.update_recent"), patch("apps.trading.engine.build_features"):
        signal = evaluate_now(strategy_config, symbol, "1h", at=datetime(2024, 1, 1, 14, 30, tzinfo=dt_timezone.utc))

    assert signal.timestamp == TS
    assert signal.baseline_side == "LONG"
