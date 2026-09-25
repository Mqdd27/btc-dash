from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.strategy.models import StrategyConfig
from apps.trading.models import EngineConfig, LiveSignal
from apps.trading.services import get_engine_config
from apps.trading.tasks import check_for_new_candle

NOW = datetime(2024, 1, 1, 14, 5, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.mark.django_db
def test_disabled_engine_never_evaluates(symbol):
    engine = get_engine_config()
    assert engine.enabled is False  # confirms the safety default

    with patch("apps.trading.tasks.evaluate_now") as mock_evaluate:
        result = check_for_new_candle()

    assert result == "disabled"
    mock_evaluate.assert_not_called()


@pytest.mark.django_db
def test_non_quant_mode_never_evaluates(symbol):
    engine = get_engine_config()
    engine.enabled = True
    engine.mode = EngineConfig.Mode.QUANT_AI
    engine.save()

    with patch("apps.trading.tasks.evaluate_now") as mock_evaluate:
        result = check_for_new_candle()

    assert "not implemented" in result
    mock_evaluate.assert_not_called()


@pytest.mark.django_db
def test_already_evaluated_candle_is_skipped(symbol):
    engine = get_engine_config()
    engine.enabled = True
    engine.mode = EngineConfig.Mode.QUANT
    engine.timeframe = "1h"
    engine.save()

    closed_candle_ts = datetime(2024, 1, 1, 13, 0, tzinfo=dt_timezone.utc)  # the 13:00-14:00 candle
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=closed_candle_ts,
        open=100, high=101, low=99, close=100, volume=1, closed=True,
    )
    snapshot = FeatureSnapshot.objects.create(symbol=symbol, timeframe="1h", timestamp=closed_candle_ts)
    LiveSignal.objects.create(
        timestamp=closed_candle_ts, symbol=symbol, timeframe="1h",
        baseline_side="WAIT", decision="WAIT", feature_snapshot=snapshot,
    )

    with patch("apps.trading.tasks.timezone") as mock_timezone, \
         patch("apps.trading.tasks.evaluate_now") as mock_evaluate:
        mock_timezone.now.return_value = NOW
        result = check_for_new_candle()

    assert result == "already evaluated"
    mock_evaluate.assert_not_called()


@pytest.mark.django_db
def test_new_candle_triggers_evaluation(symbol):
    engine = get_engine_config()
    engine.enabled = True
    engine.mode = EngineConfig.Mode.QUANT
    engine.timeframe = "1h"
    engine.save()
    StrategyConfig.objects.get_or_create(name="ema_rsi", defaults={"timeframe": "1h"})

    with patch("apps.trading.tasks.timezone") as mock_timezone, \
         patch("apps.trading.tasks.evaluate_now", return_value=None) as mock_evaluate:
        mock_timezone.now.return_value = NOW
        result = check_for_new_candle()

    mock_evaluate.assert_called_once()
    assert result == "nothing new"


@pytest.mark.django_db
def test_a_real_signal_is_handed_to_paper_trading(symbol):
    engine = get_engine_config()
    engine.enabled = True
    engine.mode = EngineConfig.Mode.QUANT
    engine.timeframe = "1h"
    engine.execution_mode = EngineConfig.ExecutionMode.PAPER
    engine.save()

    candle_ts = datetime(2024, 1, 1, 13, 0, tzinfo=dt_timezone.utc)
    candle = Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=candle_ts,
        open=100, high=101, low=99, close=100, volume=1, closed=True,
    )
    snapshot = FeatureSnapshot.objects.create(symbol=symbol, timeframe="1h", timestamp=candle_ts)
    # Not persisted: if this were a real row, the task's own "already evaluated"
    # DB check would find it and never even reach the (mocked) evaluate_now call.
    fake_signal = LiveSignal(
        timestamp=candle_ts, symbol=symbol, timeframe="1h",
        baseline_side="LONG", decision="LONG", feature_snapshot=snapshot, stop_loss=95, take_profit=110,
    )

    with patch("apps.trading.tasks.timezone") as mock_timezone, \
         patch("apps.trading.tasks.evaluate_now", return_value=fake_signal), \
         patch("apps.trading.tasks.advance_paper_trading") as mock_advance:
        mock_timezone.now.return_value = NOW
        result = check_for_new_candle()

    mock_advance.assert_called_once_with(engine, candle, fake_signal)
    assert result == "evaluated: LONG"
