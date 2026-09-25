"""The only periodic task: a cheap check (one DB query + pure time math, no
network call in steady state) for whether a new candle has closed. The heavy
pipeline (apps.trading.engine.evaluate_now) only runs when it actually has.
"""

from celery import shared_task
from django.utils import timezone

from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig
from core.execution.scheduling import latest_closed_candle_open

from .engine import evaluate_now
from .models import EngineConfig, LiveSignal
from .services import get_engine_config

DEFAULT_SYMBOL = "BTCUSDT"
# ponytail: only strategy that exists is ema_rsi -- add a "live strategy" field
# on EngineConfig when a second strategy needs to run live.
DEFAULT_STRATEGY_NAME = "ema_rsi"


@shared_task
def check_for_new_candle() -> str:
    engine = get_engine_config()
    if not engine.enabled:
        return "disabled"  # enabled=False: no evaluations, no inference, nothing
    if engine.mode != EngineConfig.Mode.QUANT:
        return f"mode {engine.mode} not implemented yet"  # only quant mode functions this phase

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
    return f"evaluated: {signal.decision}" if signal else "nothing new"
