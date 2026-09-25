from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest

from apps.agents.models import AgentDecision
from apps.agents.reviewer import ReviewOutput, daily_call_count, review_candidate
from apps.backtest.models import BacktestRun, BacktestTrade
from apps.market.models import FeatureSnapshot, MarketSymbol
from apps.ml.models import ModelVersion
from apps.strategy.models import StrategyConfig
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


@pytest.fixture
def model_version(db, strategy_config, symbol):
    return ModelVersion.objects.create(
        name="test", strategy=strategy_config, symbol=symbol, timeframe="1h",
        training_start=TS, training_end=TS, features=[], hyperparameters={},
        model_file="fake.json", active=True,
    )


def make_signal(symbol, model_version, probability, side="LONG", ts=TS):
    snapshot = FeatureSnapshot.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts, rsi_14=60, ema20_vs_ema50=0.01, atr_percent=0.02,
        rolling_volatility=0.01, volume_change=0.1, funding_rate=0.0001, open_interest_change=0.05,
    )
    return LiveSignal.objects.create(
        timestamp=ts, symbol=symbol, timeframe="1h", baseline_side=side, decision=side,
        model_probability=probability, model_version=model_version, feature_snapshot=snapshot,
        stop_loss=95, take_profit=110,
    )


@pytest.mark.django_db
def test_ai_disabled_makes_zero_calls(symbol, model_version, settings):
    settings.AI_ENABLED = False
    signal = make_signal(symbol, model_version, probability=0.9)

    with patch("apps.agents.reviewer.call_claude") as mock_call:
        result = review_candidate(signal)

    assert result is None
    mock_call.assert_not_called()
    assert signal.decision == "LONG"  # untouched


@pytest.mark.django_db
def test_below_ai_probability_threshold_makes_zero_calls(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.5)

    with patch("apps.agents.reviewer.call_claude") as mock_call:
        result = review_candidate(signal)

    assert result is None
    mock_call.assert_not_called()


@pytest.mark.django_db
def test_daily_call_limit_falls_back_to_quant_only(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    settings.AI_DAILY_CALL_LIMIT = 1
    signal1 = make_signal(symbol, model_version, probability=0.9, ts=TS)

    with patch("apps.agents.reviewer.call_claude", return_value=(ReviewOutput(decision="TAKE", confidence=0.8, reason="ok"), 10, 5, 100.0)):
        review_candidate(signal1)

    assert daily_call_count() == 1

    from datetime import timedelta
    signal2 = make_signal(symbol, model_version, probability=0.9, ts=TS + timedelta(hours=1))
    with patch("apps.agents.reviewer.call_claude") as mock_call:
        result = review_candidate(signal2)

    assert result is None  # limit reached -- fell back to quant-only
    mock_call.assert_not_called()
    assert signal2.decision == "LONG"  # unchanged, quant decision stands


@pytest.mark.django_db
def test_skip_decision_downgrades_signal_to_wait(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.9)

    with patch("apps.agents.reviewer.call_claude", return_value=(ReviewOutput(decision="SKIP", confidence=0.7, reason="too choppy"), 50, 20, 300.0)):
        decision = review_candidate(signal)

    signal.refresh_from_db()
    assert decision.decision == "SKIP"
    assert signal.decision == "WAIT"


@pytest.mark.django_db
def test_take_decision_leaves_signal_unchanged(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.9)

    with patch("apps.agents.reviewer.call_claude", return_value=(ReviewOutput(decision="TAKE", confidence=0.9, reason="strong trend"), 50, 20, 300.0)):
        review_candidate(signal)

    signal.refresh_from_db()
    assert signal.decision == "LONG"


@pytest.mark.django_db
def test_identical_context_reuses_cached_decision_without_a_new_call(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    settings.AI_MODEL = "claude-opus-5"

    signal1 = make_signal(symbol, model_version, probability=0.9, side="LONG", ts=TS)
    with patch("apps.agents.reviewer.call_claude", return_value=(ReviewOutput(decision="TAKE", confidence=0.9, reason="x"), 50, 20, 300.0)) as mock_call:
        review_candidate(signal1)
    assert mock_call.call_count == 1

    from datetime import timedelta
    # Same symbol/side/probability/feature values -> identical rendered prompt.
    signal2 = make_signal(symbol, model_version, probability=0.9, side="LONG", ts=TS + timedelta(hours=1))
    with patch("apps.agents.reviewer.call_claude") as mock_call2:
        decision2 = review_candidate(signal2)

    mock_call2.assert_not_called()
    assert decision2.cached is True
    assert decision2.decision == "TAKE"
    assert decision2.input_tokens == 0 and decision2.output_tokens == 0
    assert daily_call_count() == 1  # cache hits don't count against the daily limit


@pytest.mark.django_db
def test_historical_stats_uses_same_strategy_symbol_timeframe_side(symbol, model_version, strategy_config):
    backtest = BacktestRun.objects.create(
        strategy=strategy_config, symbol=symbol, timeframe="1h", start_date=TS, end_date=TS,
        configuration={}, initial_capital=10000, status=BacktestRun.Status.COMPLETED,
    )
    BacktestTrade.objects.create(
        backtest=backtest, side="LONG", signal_timestamp=TS, entry_timestamp=TS, entry_price=100,
        stop_loss=95, take_profit=110, size=1, fees=0, slippage=0, gross_pnl=10, net_pnl=10,
        return_pct=1.0, exit_reason="take_profit", equity_after=10010,
    )
    BacktestTrade.objects.create(
        backtest=backtest, side="LONG", signal_timestamp=TS, entry_timestamp=TS, entry_price=100,
        stop_loss=95, take_profit=110, size=1, fees=0, slippage=0, gross_pnl=-5, net_pnl=-5,
        return_pct=-0.5, exit_reason="stop_loss", equity_after=10005,
    )

    from apps.agents.reviewer import historical_stats

    signal = make_signal(symbol, model_version, probability=0.9, side="LONG")
    stats = historical_stats(signal)

    assert stats == {"sample_size": 2, "historical_win_rate_pct": 50.0}
