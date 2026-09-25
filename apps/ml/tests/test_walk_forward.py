from datetime import datetime, timedelta, timezone as dt_timezone

import numpy as np
import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.ml.models import WalkForwardRun, WalkForwardWindow
from apps.ml.walk_forward import run_walk_forward
from apps.strategy.models import StrategyConfig


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


def seed_continuous(symbol, start, n, seed=1):
    """One long continuous stretch of candles+features (alternating LONG/SHORT/
    WAIT setups over a real random walk), long enough to span several small
    walk-forward windows."""
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0, 1, n))
    candles, feats = [], []
    for i in range(n):
        ts = start + timedelta(hours=i)
        p = float(price[i])
        candles.append(Candle(
            symbol=symbol, timeframe="1h", timestamp=ts, open=p, high=p + 3, low=p - 3, close=p,
            volume=10, closed=True,
        ))
        bucket = i % 15
        if bucket < 5:
            ema_20, ema_50, rsi = 110, 100, 65
        elif bucket < 10:
            ema_20, ema_50, rsi = 100, 110, 30
        else:
            ema_20, ema_50, rsi = 100, 100, 50
        feats.append(FeatureSnapshot(
            symbol=symbol, timeframe="1h", timestamp=ts, ema_20=ema_20, ema_50=ema_50, rsi_14=rsi, atr_14=1.0,
        ))
    Candle.objects.bulk_create(candles)
    FeatureSnapshot.objects.bulk_create(feats)


@pytest.mark.django_db
def test_walk_forward_run_produces_windows_and_aggregate(symbol, strategy_config, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    start = datetime(2021, 1, 1, tzinfo=dt_timezone.utc)
    seed_continuous(symbol, start, n=24 * 150)  # ~150 days, enough for a few 1-month windows

    run = run_walk_forward(
        strategy_config, symbol, "1h", start, start + timedelta(days=149), mode="rolling",
        training_months=1, test_months=1, retrain_months=1, threshold=0.0,  # threshold 0 keeps every prediction
    )

    assert run.status == WalkForwardRun.Status.COMPLETED
    windows = list(WalkForwardWindow.objects.filter(run=run).order_by("index"))
    assert len(windows) >= 2
    for w in windows:
        assert w.train_end < w.test_start  # never trains on its own test period
        assert "total_trades" in w.metrics


@pytest.mark.django_db
def test_aggregate_metrics_only_reflect_test_window_trades(symbol, strategy_config, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    start = datetime(2021, 1, 1, tzinfo=dt_timezone.utc)
    seed_continuous(symbol, start, n=24 * 150)

    run = run_walk_forward(
        strategy_config, symbol, "1h", start, start + timedelta(days=149), mode="rolling",
        training_months=1, test_months=1, retrain_months=1, threshold=0.0,
    )

    windows = WalkForwardWindow.objects.filter(run=run)
    sum_of_window_trades = sum(w.metrics["total_trades"] for w in windows)

    # The aggregate must be exactly the concatenation of test-window trades --
    # if any training-period trade leaked in, this would exceed the window sum.
    assert run.aggregate_metrics["total_trades"] == sum_of_window_trades


@pytest.mark.django_db
def test_expanding_mode_keeps_train_start_fixed_across_windows(symbol, strategy_config, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    start = datetime(2021, 1, 1, tzinfo=dt_timezone.utc)
    seed_continuous(symbol, start, n=24 * 150)

    run = run_walk_forward(
        strategy_config, symbol, "1h", start, start + timedelta(days=149), mode="expanding",
        training_months=1, test_months=1, retrain_months=1, threshold=0.0,
    )

    windows = list(WalkForwardWindow.objects.filter(run=run).order_by("index"))
    assert len(windows) >= 2
    assert all(w.train_start == windows[0].train_start for w in windows)
