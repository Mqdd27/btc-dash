"""Live scanning engine: candle-close-driven evaluation only -- never a poll
loop. See core/execution/scheduling.py for the boundary math that decides
*whether* a new candle needs evaluating; this module does the evaluation
itself, once that's decided.

Flow (only "quant" mode is wired up this phase; quant_ai/full_agent are
accepted by EngineConfig but intentionally no-ops for now -- see
apps/trading/tasks.py):

    new finalized candle -> update data -> build latest features
    -> baseline strategy -> candidate? -> XGBoost inference
    -> probability filter -> final quant signal (LiveSignal row)

No trade is ever executed here -- this only ever produces a monitoring
record. enabled=False anywhere upstream means this module is never called.
"""

from datetime import timedelta

import pandas as pd
from django.utils import timezone

from apps.market.features import build_features
from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.market.services import update_recent
from apps.ml.dataset import ALL_FEATURE_COLUMNS, FEATURE_COLUMNS
from apps.ml.prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD, get_active_model_version, predict_win_probability
from apps.strategy.models import StrategyConfig
from core.quant.strategy import EmaRsiStrategy, Signal, StrategyParams

from .models import LiveSignal


def evaluate_now(strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str) -> LiveSignal | None:
    """Runs the full pipeline for whatever the latest finalized candle is right
    now. Returns None if there's nothing new to evaluate (already evaluated,
    or data/features for the latest candle aren't ready yet) -- idempotent,
    safe to call repeatedly.
    """
    update_recent(symbol, timeframe)  # 1. update data

    last_feature = FeatureSnapshot.objects.filter(symbol=symbol, timeframe=timeframe).order_by("-timestamp").first()
    feature_start = last_feature.timestamp if last_feature else timezone.now() - timedelta(days=30)
    build_features(symbol, timeframe, feature_start, timezone.now())  # 2. build latest features

    candle = Candle.objects.filter(symbol=symbol, timeframe=timeframe, closed=True).order_by("-timestamp").first()
    if candle is None:
        return None
    if LiveSignal.objects.filter(symbol=symbol, timeframe=timeframe, timestamp=candle.timestamp).exists():
        return None  # already evaluated this candle

    snapshot = FeatureSnapshot.objects.filter(symbol=symbol, timeframe=timeframe, timestamp=candle.timestamp).first()
    if snapshot is None:
        return None  # features not built for this candle yet

    params = StrategyParams(
        rsi_long_threshold=strategy_config.rsi_long_threshold,
        rsi_short_threshold=strategy_config.rsi_short_threshold,
        atr_sl_multiplier=strategy_config.atr_sl_multiplier,
        atr_tp_multiplier=strategy_config.atr_tp_multiplier,
    )
    baseline = EmaRsiStrategy().generate_signal(  # 3. baseline strategy
        close=float(candle.close),
        ema_fast=getattr(snapshot, f"ema_{strategy_config.ema_fast}"),
        ema_slow=getattr(snapshot, f"ema_{strategy_config.ema_slow}"),
        rsi=snapshot.rsi_14, atr=snapshot.atr_14, params=params,
    )

    probability = None
    model_version = None
    decision = Signal.WAIT

    if baseline.side is not Signal.WAIT:  # 4. candidate?
        model_version = get_active_model_version(strategy_config, symbol, timeframe)
        if model_version is not None:  # 5. XGBoost inference
            features_row = {col: getattr(snapshot, col) for col in FEATURE_COLUMNS}
            features_row["is_long"] = 1 if baseline.side is Signal.LONG else 0
            features_df = pd.DataFrame([features_row])[ALL_FEATURE_COLUMNS]
            probability = float(predict_win_probability(model_version, features_df).iloc[0])
            if probability >= DEFAULT_WIN_PROBABILITY_THRESHOLD:  # 6. probability filter
                decision = baseline.side  # 7. final quant signal
        # else: no active model yet -- can't filter, so stay WAIT rather than
        # emit an unfiltered signal in a mode whose whole point is the filter.

    return LiveSignal.objects.create(
        timestamp=candle.timestamp, symbol=symbol, timeframe=timeframe,
        baseline_side=baseline.side.value, model_probability=probability,
        decision=decision.value, model_version=model_version, feature_snapshot=snapshot,
        stop_loss=baseline.stop_loss_reference, take_profit=baseline.take_profit_reference,
    )
