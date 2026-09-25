"""Feature-engine orchestration: DB in, DB out. Math itself lives in core/features/."""

import logging

import pandas as pd

from core.features.indicators import attach_derivatives, compute_technical_features

from .models import Candle, FeatureSnapshot, FundingRate, MarketSymbol, OpenInterest

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "return_1", "return_4", "return_24", "log_return",
    "ema_10", "ema_20", "ema_50", "ema_100", "ema_200",
    "rsi_14", "macd", "macd_signal", "macd_histogram", "atr_14",
    "bollinger_upper", "bollinger_middle", "bollinger_lower", "bollinger_bandwidth",
    "rolling_volatility", "volume_sma", "volume_change", "volume_zscore",
    "distance_close_ema20", "distance_close_ema50", "distance_close_ema200",
    "ema20_vs_ema50", "ema50_vs_ema200", "atr_percent",
    "candle_body_percent", "upper_wick_percent", "lower_wick_percent",
    "funding_rate", "funding_rate_change", "open_interest", "open_interest_change",
]


def build_features(market_symbol: MarketSymbol, timeframe: str, start, end) -> int:
    """Compute + upsert FeatureSnapshot rows for [start, end].

    Reads the full finalized-candle history up to `end` (not just [start, end])
    so long-window indicators like EMA 200 are warmed up correctly, then only
    writes snapshot rows inside the requested range. Idempotent: re-running the
    same or overlapping range just recomputes and overwrites those rows -- safe
    to call repeatedly (e.g. incrementally, with start=last known feature time).
    """
    candles = list(
        Candle.objects.filter(
            symbol=market_symbol, timeframe=timeframe, closed=True, timestamp__lte=end
        )
        .order_by("timestamp")
        .values("timestamp", "open", "high", "low", "close", "volume")
    )
    if not candles:
        return 0

    candle_df = pd.DataFrame(candles)
    candle_df["timestamp"] = pd.to_datetime(candle_df["timestamp"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        candle_df[col] = candle_df[col].astype(float)

    features = compute_technical_features(candle_df)

    funding_df = pd.DataFrame(
        FundingRate.objects.filter(symbol=market_symbol, timestamp__lte=end)
        .order_by("timestamp")
        .values("timestamp", "funding_rate")
    )
    if not funding_df.empty:
        funding_df["timestamp"] = pd.to_datetime(funding_df["timestamp"], utc=True)
        funding_df["funding_rate"] = funding_df["funding_rate"].astype(float)

    oi_df = pd.DataFrame(
        OpenInterest.objects.filter(symbol=market_symbol, timestamp__lte=end)
        .order_by("timestamp")
        .values("timestamp", "open_interest")
    )
    if not oi_df.empty:
        oi_df["timestamp"] = pd.to_datetime(oi_df["timestamp"], utc=True)
        oi_df["open_interest"] = oi_df["open_interest"].astype(float)

    features = attach_derivatives(features, funding_df, oi_df)
    features = features[(features["timestamp"] >= start) & (features["timestamp"] <= end)]

    snapshots = [
        FeatureSnapshot(
            symbol=market_symbol,
            timeframe=timeframe,
            timestamp=row["timestamp"],
            **{col: _clean(row[col]) for col in FEATURE_COLUMNS},
        )
        for row in features.to_dict("records")
    ]
    if not snapshots:
        return 0

    FeatureSnapshot.objects.bulk_create(
        snapshots,
        update_conflicts=True,
        unique_fields=["symbol", "timeframe", "timestamp"],
        update_fields=FEATURE_COLUMNS,
    )
    return len(snapshots)


def _clean(value):
    return None if pd.isna(value) else float(value)


def get_feature_stats(symbol_code: str, timeframe: str) -> dict:
    try:
        market_symbol = MarketSymbol.objects.get(symbol=symbol_code)
    except MarketSymbol.DoesNotExist:
        return None

    snapshots = FeatureSnapshot.objects.filter(symbol=market_symbol, timeframe=timeframe)
    first = snapshots.order_by("timestamp").first()
    last = snapshots.order_by("-timestamp").first()

    return {
        "candle_count": Candle.objects.filter(
            symbol=market_symbol, timeframe=timeframe, closed=True
        ).count(),
        "feature_count": snapshots.count(),
        "first_feature_timestamp": first.timestamp if first else None,
        "last_feature_timestamp": last.timestamp if last else None,
    }
