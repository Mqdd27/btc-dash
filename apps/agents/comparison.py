"""Backtest comparison: A (baseline strategy) vs B (quant/XGBoost) vs C (quant
+ single AI reviewer) vs D (quant + TradingAgents), over the same historical
range. A and B are pure quant -- no AI, ever. C and D replay the AI review
logic against historical candidates, so they cost real API calls (mitigated
by the same prompt_hash+model caching every other AI path in this project
uses) -- run them over a small range unless you mean to spend on a big one.
"""

import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.backtest.services import DEFAULT_ENGINE_CONFIG, load_candle_bars, load_signal_inputs
from apps.market.models import MarketSymbol
from apps.ml.dataset import ALL_FEATURE_COLUMNS, FEATURE_COLUMNS
from apps.ml.prediction import get_active_model_version, predict_win_probability
from apps.strategy.models import SignalCandidate, StrategyConfig
from core.quant.backtest import BacktestEngineConfig, SignalInput, run_engine
from core.quant.metrics import compute_metrics

from .models import AgentDecision, AgentStepDecision
from .reviewer import review_candidate
from .trading_agents import run_trading_agents

METRIC_KEYS = ["total_return_pct", "final_capital", "profit_factor", "max_drawdown_pct", "sharpe_ratio", "total_trades"]


def _historical_live_signal(strategy_config, symbol, timeframe, candidate: SignalCandidate):
    """Reuses (or creates) the LiveSignal a real live evaluation would have
    produced for this historical candidate, so review_candidate()/
    run_trading_agents() -- built for the live path -- work unchanged here.
    """
    from apps.trading.models import LiveSignal

    existing = LiveSignal.objects.filter(
        symbol=symbol, timeframe=timeframe, timestamp=candidate.candle_timestamp
    ).first()
    if existing is not None:
        return existing

    model_version = get_active_model_version(strategy_config, symbol, timeframe)
    probability = None
    if model_version is not None:
        row = {col: getattr(candidate.feature_snapshot, col) for col in FEATURE_COLUMNS}
        row["is_long"] = 1 if candidate.side == "LONG" else 0
        df = pd.DataFrame([row])[ALL_FEATURE_COLUMNS]
        probability = float(predict_win_probability(model_version, df).iloc[0])

    # Mirrors evaluate_now(): the quant decision (before any AI review layer)
    # is WAIT unless XGBoost actually cleared the threshold -- never default
    # to "approved", or a signal with no model/low probability would leak
    # into C/D's trade list despite review_fn correctly making zero calls.
    quant_decision = (
        candidate.side if probability is not None and probability >= settings.AI_MIN_QUANT_PROBABILITY
        else LiveSignal.Side.WAIT
    )

    return LiveSignal.objects.create(
        timestamp=candidate.candle_timestamp, symbol=symbol, timeframe=timeframe,
        baseline_side=candidate.side, decision=quant_decision, model_probability=probability,
        model_version=model_version, feature_snapshot=candidate.feature_snapshot,
        stop_loss=candidate.stop_loss_reference, take_profit=candidate.take_profit_reference,
    )


def _ai_filtered_signals(strategy_config, symbol, timeframe, start, end, review_fn) -> list[SignalInput]:
    candidates = SignalCandidate.objects.filter(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe,
        candle_timestamp__gte=start, candle_timestamp__lte=end,
    ).select_related("feature_snapshot")

    kept = []
    for candidate in candidates:
        live_signal = _historical_live_signal(strategy_config, symbol, timeframe, candidate)
        review_fn(live_signal)  # mutates live_signal.decision in place; no-op if AI disabled/ineligible
        if live_signal.decision in ("LONG", "SHORT"):
            kept.append(SignalInput(
                timestamp=live_signal.timestamp, side=live_signal.decision,
                stop_loss=live_signal.stop_loss, take_profit=live_signal.take_profit,
            ))
    return kept


def _ai_spend_since(cutoff) -> dict:
    real_decisions = AgentDecision.objects.filter(cached=False, created_at__gte=cutoff)
    real_steps = AgentStepDecision.objects.filter(cached=False, created_at__gte=cutoff)
    calls = real_decisions.count() + real_steps.count()
    tokens = sum(d.input_tokens + d.output_tokens for d in real_decisions) + sum(
        s.input_tokens + s.output_tokens for s in real_steps
    )
    cost = sum(d.estimated_cost or 0 for d in real_decisions) + sum(s.estimated_cost or 0 for s in real_steps)
    return {"ai_calls": calls, "ai_tokens": tokens, "estimated_ai_cost": cost}


def _summarize(trades, ai_spend: dict | None = None) -> dict:
    metrics = compute_metrics(trades, initial_capital=10000)
    result = {k: metrics[k] for k in METRIC_KEYS}
    result.update(ai_spend or {"ai_calls": 0, "ai_tokens": 0, "estimated_ai_cost": 0})
    return result


def compare_strategies(strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, start, end) -> dict:
    engine_config = BacktestEngineConfig(initial_capital=10000, **DEFAULT_ENGINE_CONFIG)
    candles = load_candle_bars(symbol, timeframe, start, end)
    all_signals = load_signal_inputs(strategy_config, symbol, timeframe, start, end)

    # A: baseline strategy, every candidate, no XGBoost/AI filtering at all.
    baseline_trades, _ = run_engine(candles, all_signals, engine_config)

    # B: quant/XGBoost -- every candidate whose predicted P(win) clears the
    # same threshold C/D gate on, so B is exactly what C/D start from before
    # AI review is applied.
    model_version = get_active_model_version(strategy_config, symbol, timeframe)
    xgboost_signals = _probability_filtered_signals(strategy_config, symbol, timeframe, start, end, model_version)
    xgboost_trades, _ = run_engine(candles, xgboost_signals, engine_config)

    ai_cutoff = timezone.now()
    ai_reviewer_signals = _ai_filtered_signals(strategy_config, symbol, timeframe, start, end, review_candidate)
    ai_reviewer_spend = _ai_spend_since(ai_cutoff)
    ai_reviewer_trades, _ = run_engine(candles, ai_reviewer_signals, engine_config)

    trading_agents_cutoff = timezone.now()
    trading_agents_signals = _ai_filtered_signals(strategy_config, symbol, timeframe, start, end, run_trading_agents)
    trading_agents_spend = _ai_spend_since(trading_agents_cutoff)
    trading_agents_trades, _ = run_engine(candles, trading_agents_signals, engine_config)

    return {
        "A_baseline": _summarize(baseline_trades),
        "B_quant_xgboost": _summarize(xgboost_trades),
        "C_quant_ai_reviewer": _summarize(ai_reviewer_trades, ai_reviewer_spend),
        "D_quant_trading_agents": _summarize(trading_agents_trades, trading_agents_spend),
    }


def _probability_filtered_signals(strategy_config, symbol, timeframe, start, end, model_version) -> list[SignalInput]:
    if model_version is None:
        return []

    candidates = SignalCandidate.objects.filter(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe,
        candle_timestamp__gte=start, candle_timestamp__lte=end,
    ).select_related("feature_snapshot")

    kept = []
    for candidate in candidates:
        row = {col: getattr(candidate.feature_snapshot, col) for col in FEATURE_COLUMNS}
        row["is_long"] = 1 if candidate.side == "LONG" else 0
        df = pd.DataFrame([row])[ALL_FEATURE_COLUMNS]
        probability = float(predict_win_probability(model_version, df).iloc[0])
        if probability >= settings.AI_MIN_QUANT_PROBABILITY:
            kept.append(SignalInput(
                timestamp=candidate.candle_timestamp, side=candidate.side,
                stop_loss=candidate.stop_loss_reference, take_profit=candidate.take_profit_reference,
            ))
    return kept
