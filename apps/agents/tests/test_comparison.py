from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest

from apps.agents.comparison import compare_strategies
from apps.market.models import MarketSymbol
from apps.ml.models import ModelVersion
from apps.strategy.models import StrategyConfig
from apps.strategy.services import generate_signals

from ...ml.tests.test_dataset import seed_window  # reuse the established candle+feature seeder


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


@pytest.mark.django_db
def test_baseline_includes_everything_but_xgboost_variant_is_empty_without_a_model(symbol, strategy_config):
    start, end = seed_window(symbol, datetime(2021, 1, 1, tzinfo=dt_timezone.utc), 60, seed=1)
    generate_signals(strategy_config, symbol, "1h", start, end)

    results = compare_strategies(strategy_config, symbol, "1h", start, end)

    assert results["A_baseline"]["total_trades"] > 0
    assert results["B_quant_xgboost"]["total_trades"] == 0  # no active model -> nothing clears the gate
    assert results["C_quant_ai_reviewer"]["total_trades"] == 0
    assert results["D_quant_trading_agents"]["total_trades"] == 0
    for variant in ("C_quant_ai_reviewer", "D_quant_trading_agents"):
        assert results[variant]["ai_calls"] == 0  # nothing to review -> zero spend


@pytest.mark.django_db
def test_ai_spend_is_tracked_separately_for_c_and_d(symbol, strategy_config, settings):
    settings.AI_ENABLED = True
    settings.AI_MIN_QUANT_PROBABILITY = 0.5

    start, end = seed_window(symbol, datetime(2021, 1, 1, tzinfo=dt_timezone.utc), 60, seed=1)
    generate_signals(strategy_config, symbol, "1h", start, end)
    ModelVersion.objects.create(
        name="test", strategy=strategy_config, symbol=symbol, timeframe="1h",
        training_start=start, training_end=end, features=[], hyperparameters={},
        model_file="fake.json", active=True,
    )

    from apps.agents.trading_agents import RiskReview, TechnicalView

    with patch("apps.agents.comparison.predict_win_probability") as mock_predict, \
         patch("apps.agents.reviewer.call_claude") as mock_reviewer_call, \
         patch("apps.agents.trading_agents.call_claude_structured") as mock_agents_call:
        import pandas as pd
        mock_predict.return_value = pd.Series([0.9])  # every candidate clears the gate

        from apps.agents.reviewer import ReviewOutput
        mock_reviewer_call.return_value = (ReviewOutput(decision="TAKE", confidence=0.9, reason="x"), 10, 5, 50.0)

        from apps.agents.trading_agents import DerivativesView, ResearchThesis, TraderDecision
        mock_agents_call.side_effect = lambda *a, **k: {
            TechnicalView: (TechnicalView(trend="bullish", strength=0.8, notes="x"), 10, 5, 50.0),
            DerivativesView: (DerivativesView(positioning="neutral", risk_flag=False, notes="x"), 10, 5, 50.0),
            ResearchThesis: (ResearchThesis(thesis="x", confidence=0.7), 10, 5, 50.0),
            TraderDecision: (TraderDecision(decision="LONG", confidence=0.8, reasoning="x"), 10, 5, 50.0),
            RiskReview: (RiskReview(approved=True, reason="x"), 10, 5, 50.0),
        }[a[2]]

        results = compare_strategies(strategy_config, symbol, "1h", start, end)

    assert results["B_quant_xgboost"]["total_trades"] > 0
    assert results["C_quant_ai_reviewer"]["ai_calls"] > 0
    assert results["C_quant_ai_reviewer"]["estimated_ai_cost"] > 0
    assert results["D_quant_trading_agents"]["ai_calls"] > 0
    # D runs 6 real steps per candidate vs C's 1 real call per candidate
    assert results["D_quant_trading_agents"]["ai_calls"] > results["C_quant_ai_reviewer"]["ai_calls"]
