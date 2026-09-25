from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.strategy.models import SignalCandidate, StrategyConfig
from apps.strategy.services import generate_signals

START = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


def make_snapshot(symbol, ts, close, ema_20=110, ema_50=100, rsi_14=60, atr_14=2.0):
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts,
        open=close, high=close, low=close, close=close, volume=1, closed=True,
    )
    return FeatureSnapshot.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts, ema_20=ema_20, ema_50=ema_50,
        rsi_14=rsi_14, atr_14=atr_14,
    )


@pytest.mark.django_db
def test_generate_signals_creates_long_candidate(symbol, strategy_config):
    ts = START
    make_snapshot(symbol, ts, close=100, ema_20=110, ema_50=100, rsi_14=60, atr_14=2.0)

    count = generate_signals(strategy_config, symbol, "1h", ts, ts)

    assert count == 1
    candidate = SignalCandidate.objects.get()
    assert candidate.side == "LONG"
    assert candidate.entry_reference_price == 100.0
    assert candidate.stop_loss_reference == 100.0 - 1.5 * 2.0
    assert candidate.take_profit_reference == 100.0 + 3.0 * 2.0


@pytest.mark.django_db
def test_wait_produces_no_candidate(symbol, strategy_config):
    make_snapshot(symbol, START, close=100, ema_20=100, ema_50=100, rsi_14=50, atr_14=2.0)

    count = generate_signals(strategy_config, symbol, "1h", START, START)

    assert count == 0
    assert SignalCandidate.objects.count() == 0


@pytest.mark.django_db
def test_duplicate_candidate_prevention(symbol, strategy_config):
    ts = START
    make_snapshot(symbol, ts, close=100, ema_20=110, ema_50=100, rsi_14=60, atr_14=2.0)

    generate_signals(strategy_config, symbol, "1h", ts, ts)
    generate_signals(strategy_config, symbol, "1h", ts, ts)

    assert SignalCandidate.objects.count() == 1


@pytest.mark.django_db
def test_signal_at_t_unaffected_by_later_candle(symbol, strategy_config):
    t = START
    make_snapshot(symbol, t, close=100, ema_20=110, ema_50=100, rsi_14=60, atr_14=2.0)
    generate_signals(strategy_config, symbol, "1h", t, t)
    before = SignalCandidate.objects.get()
    values_before = (before.entry_reference_price, before.stop_loss_reference, before.take_profit_reference)

    # A wildly different candle/feature snapshot appears *after* T.
    t_plus_1 = t + timedelta(hours=1)
    make_snapshot(symbol, t_plus_1, close=99999, ema_20=1, ema_50=99999, rsi_14=1, atr_14=500)
    generate_signals(strategy_config, symbol, "1h", t, t_plus_1)

    after = SignalCandidate.objects.get(candle_timestamp=t)
    values_after = (after.entry_reference_price, after.stop_loss_reference, after.take_profit_reference)
    assert values_before == values_after
