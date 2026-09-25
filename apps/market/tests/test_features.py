from datetime import datetime, timedelta, timezone as dt_timezone

import numpy as np
import pytest

from apps.market.features import build_features, get_feature_stats
from apps.market.models import Candle, FeatureSnapshot, MarketSymbol

START = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


def make_candles(symbol, n=260, seed=0):
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 1, n))
    rows = []
    for i in range(n):
        ts = START + timedelta(hours=i)
        c = price[i]
        rows.append(
            Candle(
                symbol=symbol, timeframe="1h", timestamp=ts,
                open=c - 0.1, high=c + 0.5, low=c - 0.5, close=c,
                volume=100 + i % 10, closed=True,
            )
        )
    Candle.objects.bulk_create(rows)
    return [r.timestamp for r in rows]


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.mark.django_db
def test_snapshot_at_t_is_unchanged_by_later_candle(symbol):
    timestamps = make_candles(symbol, n=250)
    t = timestamps[-1]

    build_features(symbol, "1h", START, t)
    snapshot_before = FeatureSnapshot.objects.get(symbol=symbol, timeframe="1h", timestamp=t)
    values_before = {f: getattr(snapshot_before, f) for f in ("ema_20", "rsi_14", "macd", "return_1")}

    # Append T+1 with a wildly different price -- must not leak backward into T.
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=t + timedelta(hours=1),
        open=99999, high=99999, low=99999, close=99999, volume=1, closed=True,
    )
    build_features(symbol, "1h", START, t + timedelta(hours=1))
    snapshot_after = FeatureSnapshot.objects.get(symbol=symbol, timeframe="1h", timestamp=t)
    values_after = {f: getattr(snapshot_after, f) for f in ("ema_20", "rsi_14", "macd", "return_1")}

    assert values_before == values_after


@pytest.mark.django_db
def test_build_features_is_idempotent(symbol):
    timestamps = make_candles(symbol, n=250)
    build_features(symbol, "1h", START, timestamps[-1])
    count_first = FeatureSnapshot.objects.count()

    build_features(symbol, "1h", START, timestamps[-1])
    count_second = FeatureSnapshot.objects.count()

    assert count_first == count_second == 250


@pytest.mark.django_db
def test_incremental_build_only_touches_requested_range(symbol):
    timestamps = make_candles(symbol, n=250)
    midpoint = timestamps[150]

    build_features(symbol, "1h", START, midpoint)
    assert FeatureSnapshot.objects.count() == 151

    build_features(symbol, "1h", midpoint + timedelta(hours=1), timestamps[-1])
    assert FeatureSnapshot.objects.count() == 250


@pytest.mark.django_db
def test_feature_stats(symbol):
    timestamps = make_candles(symbol, n=10)
    assert get_feature_stats("BTCUSDT", "1h")["feature_count"] == 0

    build_features(symbol, "1h", START, timestamps[-1])
    stats = get_feature_stats("BTCUSDT", "1h")
    assert stats["candle_count"] == 10
    assert stats["feature_count"] == 10
    assert stats["first_feature_timestamp"] == timestamps[0]
    assert stats["last_feature_timestamp"] == timestamps[-1]
