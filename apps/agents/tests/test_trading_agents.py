from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

import pytest

from apps.agents.models import AgentPipelineRun, AgentStepDecision
from apps.agents.trading_agents import (
    DerivativesView, ResearchThesis, RiskReview, SentimentView, TechnicalView, TraderDecision, run_trading_agents,
)
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


def mock_step_outputs(approve: bool, trader_side: str = "LONG"):
    """One (parsed, input_tokens, output_tokens, latency_ms) tuple per real call,
    in the order run_trading_agents makes them: technical, derivatives, bull,
    bear, trader, risk. (sentiment is a local stub, never calls the mock.)"""
    return [
        (TechnicalView(trend="bullish", strength=0.8, notes="x"), 50, 20, 100.0),
        (DerivativesView(positioning="neutral", risk_flag=False, notes="x"), 50, 20, 100.0),
        (ResearchThesis(thesis="bull case", confidence=0.8), 50, 20, 100.0),
        (ResearchThesis(thesis="bear case", confidence=0.3), 50, 20, 100.0),
        (TraderDecision(decision=trader_side, confidence=0.8, reasoning="x"), 50, 20, 100.0),
        (RiskReview(approved=approve, reason="x"), 50, 20, 100.0),
    ]


@pytest.mark.django_db
def test_disabled_makes_zero_calls(symbol, model_version, settings):
    settings.AI_ENABLED = False
    signal = make_signal(symbol, model_version, probability=0.9)

    with patch("apps.agents.trading_agents.call_claude_structured") as mock_call:
        result = run_trading_agents(signal)

    assert result is None
    mock_call.assert_not_called()
    assert signal.decision == "LONG"


@pytest.mark.django_db
def test_below_probability_threshold_makes_zero_calls(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.5)

    with patch("apps.agents.trading_agents.call_claude_structured") as mock_call:
        result = run_trading_agents(signal)

    assert result is None
    mock_call.assert_not_called()


@pytest.mark.django_db
def test_full_pipeline_runs_six_real_steps_plus_one_free_sentiment_stub(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.9)

    with patch("apps.agents.trading_agents.call_claude_structured", side_effect=mock_step_outputs(approve=True)):
        run = run_trading_agents(signal)

    steps = AgentStepDecision.objects.filter(pipeline_run=run)
    assert steps.count() == 7
    assert {s.agent_name for s in steps} == {
        "technical_analyst", "derivatives_analyst", "sentiment_analyst",
        "bull_researcher", "bear_researcher", "trader", "risk_reviewer",
    }
    sentiment_step = steps.get(agent_name="sentiment_analyst")
    assert sentiment_step.cached is True
    assert sentiment_step.input_tokens == 0
    assert steps.exclude(agent_name="sentiment_analyst").filter(cached=False).count() == 6


@pytest.mark.django_db
def test_risk_reviewer_veto_downgrades_signal_to_wait(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.9, side="LONG")

    with patch("apps.agents.trading_agents.call_claude_structured", side_effect=mock_step_outputs(approve=False, trader_side="LONG")):
        run = run_trading_agents(signal)

    signal.refresh_from_db()
    assert run.final_recommendation == "WAIT"
    assert signal.decision == "WAIT"


@pytest.mark.django_db
def test_risk_reviewer_approval_sets_final_decision_to_traders_call(symbol, model_version, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.65
    signal = make_signal(symbol, model_version, probability=0.9, side="LONG")

    with patch("apps.agents.trading_agents.call_claude_structured", side_effect=mock_step_outputs(approve=True, trader_side="LONG")):
        run = run_trading_agents(signal)

    signal.refresh_from_db()
    assert run.final_recommendation == "LONG"
    assert signal.decision == "LONG"
    assert run.total_input_tokens == 6 * 50
    assert run.total_output_tokens == 6 * 20


@pytest.mark.django_db
def test_daily_budget_is_shared_with_the_single_reviewer(symbol, model_version, settings):
    """Phase 11's AgentDecision real calls count against the same daily limit
    the full_agent pipeline checks -- one shared AI budget."""
    from apps.agents.models import AgentDecision

    settings.AI_ENABLED = True
    settings.AI_DAILY_CALL_LIMIT = 1
    other_signal = make_signal(symbol, model_version, probability=0.9, ts=TS)
    AgentDecision.objects.create(
        signal=other_signal, model=settings.AI_MODEL, prompt_hash="x" * 64, decision="TAKE",
        confidence=0.9, reason="x", input_tokens=10, output_tokens=5, estimated_cost=0.001,
        latency_ms=100, cached=False,
    )

    signal = make_signal(symbol, model_version, probability=0.9, ts=TS + timedelta(hours=1))
    with patch("apps.agents.trading_agents.call_claude_structured") as mock_call:
        result = run_trading_agents(signal)

    assert result is None  # budget already spent by the Phase 11 call above
    mock_call.assert_not_called()
