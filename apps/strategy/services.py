"""Orchestration: read FeatureSnapshot + Candle, run a strategy, store SignalCandidates."""

from apps.market.models import Candle, MarketSymbol
from core.quant.strategy import EmaRsiStrategy, Signal, StrategyParams

from .models import FeatureSnapshot, SignalCandidate, StrategyConfig

STRATEGIES = {"ema_rsi": EmaRsiStrategy}


def generate_signals(strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, start, end) -> int:
    strategy_cls = STRATEGIES[strategy_config.name]
    strategy = strategy_cls()
    params = StrategyParams(
        rsi_long_threshold=strategy_config.rsi_long_threshold,
        rsi_short_threshold=strategy_config.rsi_short_threshold,
        atr_sl_multiplier=strategy_config.atr_sl_multiplier,
        atr_tp_multiplier=strategy_config.atr_tp_multiplier,
    )
    ema_fast_field = f"ema_{strategy_config.ema_fast}"
    ema_slow_field = f"ema_{strategy_config.ema_slow}"

    snapshots = FeatureSnapshot.objects.filter(
        symbol=symbol, timeframe=timeframe, timestamp__gte=start, timestamp__lte=end
    ).order_by("timestamp")
    closes = dict(
        Candle.objects.filter(
            symbol=symbol, timeframe=timeframe, timestamp__gte=start, timestamp__lte=end
        ).values_list("timestamp", "close")
    )

    candidates = []
    for snapshot in snapshots:
        close = closes.get(snapshot.timestamp)
        if close is None:
            continue

        result = strategy.generate_signal(
            close=float(close),
            ema_fast=getattr(snapshot, ema_fast_field),
            ema_slow=getattr(snapshot, ema_slow_field),
            rsi=snapshot.rsi_14,
            atr=snapshot.atr_14,
            params=params,
        )
        if result.side is Signal.WAIT:
            continue

        candidates.append(
            SignalCandidate(
                strategy=strategy_config,
                symbol=symbol,
                timeframe=timeframe,
                candle_timestamp=snapshot.timestamp,
                side=result.side.value,
                entry_reference_price=result.entry_reference_price,
                stop_loss_reference=result.stop_loss_reference,
                take_profit_reference=result.take_profit_reference,
                feature_snapshot=snapshot,
                strategy_version=strategy.version,
            )
        )

    if not candidates:
        return 0

    SignalCandidate.objects.bulk_create(
        candidates,
        update_conflicts=True,
        unique_fields=["strategy", "symbol", "timeframe", "candle_timestamp"],
        update_fields=[
            "side", "entry_reference_price", "stop_loss_reference",
            "take_profit_reference", "feature_snapshot", "strategy_version",
        ],
    )
    return len(candidates)
