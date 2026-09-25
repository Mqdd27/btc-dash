"""The only periodic task: a cheap check (one DB query + pure time math, no
network call in steady state) for whether a new candle has closed. The heavy
pipeline (apps.trading.engine.evaluate_now) only runs when it actually has.
"""

from celery import shared_task
from django.utils import timezone

from apps.market.models import Candle
from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig
from core.execution.scheduling import latest_closed_candle_open

from .engine import evaluate_now
from .models import EngineConfig, LiveSignal
from .paper import advance_paper_trading
from .services import get_engine_config

IMPLEMENTED_MODES = (EngineConfig.Mode.QUANT, EngineConfig.Mode.QUANT_AI, EngineConfig.Mode.FULL_AGENT)

DEFAULT_SYMBOL = "BTCUSDT"
# ponytail: only strategy that exists is ema_rsi -- add a "live strategy" field
# on EngineConfig when a second strategy needs to run live.
DEFAULT_STRATEGY_NAME = "ema_rsi"


@shared_task
def check_for_new_candle() -> str:
    engine = get_engine_config()
    if not engine.enabled:
        return "disabled"  # enabled=False: no evaluations, no inference, nothing
    if engine.mode not in IMPLEMENTED_MODES:
        return f"mode {engine.mode} not implemented yet"  # defensive: all 3 defined modes are implemented now

    symbol = resolve_market_symbol(DEFAULT_SYMBOL)
    expected = latest_closed_candle_open(timezone.now(), engine.timeframe)

    already_evaluated = LiveSignal.objects.filter(
        symbol=symbol, timeframe=engine.timeframe, timestamp__gte=expected
    ).exists()
    if already_evaluated:
        return "already evaluated"

    strategy_config, _ = StrategyConfig.objects.get_or_create(
        name=DEFAULT_STRATEGY_NAME, defaults={"timeframe": engine.timeframe}
    )
    signal = evaluate_now(strategy_config, symbol, engine.timeframe)
    if signal is None:
        return "nothing new"

    if signal.decision in (LiveSignal.Side.LONG, LiveSignal.Side.SHORT):
        if engine.mode == EngineConfig.Mode.QUANT_AI:
            from apps.agents.reviewer import review_candidate

            review_candidate(signal)  # may downgrade signal.decision to WAIT in place; no-op if AI_ENABLED=False
        elif engine.mode == EngineConfig.Mode.FULL_AGENT:
            from apps.agents.trading_agents import run_trading_agents

            run_trading_agents(signal)  # may set signal.decision to the Trader's call, or WAIT; no-op if AI_ENABLED=False

    candle = Candle.objects.get(symbol=symbol, timeframe=engine.timeframe, timestamp=signal.timestamp)
    advance_paper_trading(engine, candle, signal)  # no-op unless execution_mode == "paper"
    return f"evaluated: {signal.decision}"
