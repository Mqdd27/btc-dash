from datetime import datetime, timedelta, timezone as dt_timezone

import numpy as np
import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.ml.dataset import ALL_FEATURE_COLUMNS, LABEL_COLUMN, build_ml_dataset, build_split_dataset, load_split
from apps.strategy.models import StrategyConfig

LEAKY_COLUMNS = {"net_pnl", "exit_price", "exit_reason", "gross_pnl", "return_pct", "high", "low", "close"}


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


def seed_window(symbol, start, n, seed):
    """A window of candles+features with alternating LONG/SHORT/WAIT setups over
    a real random-walk price, so both WIN and LOSS outcomes actually occur."""
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 1, n))
    for i in range(n):
        ts = start + timedelta(hours=i)
        p = float(price[i])
        Candle.objects.create(
            symbol=symbol, timeframe="1h", timestamp=ts,
            open=p, high=p + 3, low=p - 3, close=p, volume=10, closed=True,
        )
        bucket = i % 15
        if bucket < 5:
            ema_20, ema_50, rsi = 110, 100, 65  # LONG setup
        elif bucket < 10:
            ema_20, ema_50, rsi = 100, 110, 30  # SHORT setup
        else:
            ema_20, ema_50, rsi = 100, 100, 50  # WAIT
        FeatureSnapshot.objects.create(
            symbol=symbol, timeframe="1h", timestamp=ts,
            ema_20=ema_20, ema_50=ema_50, rsi_14=rsi, atr_14=1.0,
        )
    return start, start + timedelta(hours=n - 1)


def seed_ml_data(symbol, n_per_split=200):
    """Three contiguous, non-overlapping windows standing in for train/val/test."""
    train = seed_window(symbol, datetime(2021, 1, 1, tzinfo=dt_timezone.utc), n_per_split, seed=1)
    val = seed_window(symbol, datetime(2022, 1, 1, tzinfo=dt_timezone.utc), n_per_split, seed=2)
    test = seed_window(symbol, datetime(2023, 1, 1, tzinfo=dt_timezone.utc), n_per_split, seed=3)
    return {
        "train": (train[0].date().isoformat(), train[1].date().isoformat()),
        "validation": (val[0].date().isoformat(), val[1].date().isoformat()),
        "test": (test[0].date().isoformat(), test[1].date().isoformat()),
    }


@pytest.mark.django_db
def test_build_split_dataset_labels_from_realized_pnl(symbol, strategy_config):
    start, end = seed_window(symbol, datetime(2021, 1, 1, tzinfo=dt_timezone.utc), 200, seed=1)

    df = build_split_dataset(strategy_config, symbol, "1h", start, end)

    assert not df.empty
    assert set(df[LABEL_COLUMN].unique()) <= {0, 1}
    assert set(ALL_FEATURE_COLUMNS).issubset(df.columns)


@pytest.mark.django_db
def test_dataset_never_includes_leaky_columns(symbol, strategy_config):
    start, end = seed_window(symbol, datetime(2021, 1, 1, tzinfo=dt_timezone.utc), 200, seed=1)

    df = build_split_dataset(strategy_config, symbol, "1h", start, end)

    assert not LEAKY_COLUMNS & set(df.columns)


@pytest.mark.django_db
def test_build_ml_dataset_writes_three_splits_and_they_round_trip(symbol, strategy_config, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    splits = seed_ml_data(symbol)

    paths = build_ml_dataset(strategy_config, symbol, "1h", splits=splits)

    assert set(paths) == {"train", "validation", "test"}
    for split in paths:
        df = load_split(strategy_config, symbol, "1h", split)
        assert not df.empty
        assert LABEL_COLUMN in df.columns
