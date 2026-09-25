from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.trading.models import EngineConfig, LiveSignal, PaperPosition, PaperTrade
from apps.trading.paper import advance_paper_trading, get_paper_account

T0 = datetime(2024, 1, 1, 14, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def engine_config(db):
    return EngineConfig.objects.create(execution_mode=EngineConfig.ExecutionMode.PAPER, timeframe="1h")


def make_candle(symbol, ts, open, high, low, close):
    return Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=ts, open=open, high=high, low=low, close=close,
        volume=1, closed=True,
    )


def make_signal(symbol, ts, decision, stop_loss=None, take_profit=None):
    snapshot = FeatureSnapshot.objects.create(symbol=symbol, timeframe="1h", timestamp=ts)
    return LiveSignal.objects.create(
        timestamp=ts, symbol=symbol, timeframe="1h", baseline_side=decision, decision=decision,
        feature_snapshot=snapshot, stop_loss=stop_loss, take_profit=take_profit,
    )


@pytest.mark.django_db
def test_long_signal_queues_pending_position(symbol, engine_config):
    candle = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    signal = make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110)

    advance_paper_trading(engine_config, candle, signal)

    position = PaperPosition.objects.get()
    assert position.status == PaperPosition.Status.PENDING
    assert position.entry_price is None  # not filled yet -- fills on the *next* candle's open


@pytest.mark.django_db
def test_pending_position_fills_at_next_candle_open(symbol, engine_config):
    candle0 = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    signal0 = make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110)
    advance_paper_trading(engine_config, candle0, signal0)

    t1 = T0 + timedelta(hours=1)
    candle1 = make_candle(symbol, t1, open=101, high=102, low=100, close=101)
    signal1 = make_signal(symbol, t1, "WAIT")
    advance_paper_trading(engine_config, candle1, signal1)

    position = PaperPosition.objects.get()
    assert position.status == PaperPosition.Status.OPEN
    assert position.entry_price == pytest.approx(101 * 1.0005)  # candle1's open (+slippage), not candle0's close
    assert position.entry_timestamp == t1


@pytest.mark.django_db
def test_open_position_closes_on_stop_loss(symbol, engine_config):
    candle0 = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    signal0 = make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110)
    advance_paper_trading(engine_config, candle0, signal0)

    t1 = T0 + timedelta(hours=1)
    candle1 = make_candle(symbol, t1, open=101, high=101, low=101, close=101)  # fills here
    advance_paper_trading(engine_config, candle1, make_signal(symbol, t1, "WAIT"))

    t2 = t1 + timedelta(hours=1)
    candle2 = make_candle(symbol, t2, open=100, high=100, low=90, close=94)  # dips through SL=95
    advance_paper_trading(engine_config, candle2, make_signal(symbol, t2, "WAIT"))

    position = PaperPosition.objects.get()
    assert position.status == PaperPosition.Status.CLOSED
    trade = PaperTrade.objects.get(position=position)
    assert trade.exit_reason == "stop_loss"
    assert trade.pnl < 0


@pytest.mark.django_db
def test_pausing_stops_new_positions_but_keeps_monitoring_open_ones(symbol, engine_config):
    account = get_paper_account()
    account.paused = True
    account.save()

    candle = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    signal = make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110)
    advance_paper_trading(engine_config, candle, signal)

    assert PaperPosition.objects.count() == 0  # paused -- nothing queued


@pytest.mark.django_db
def test_pausing_never_deletes_existing_positions_or_trades(symbol, engine_config):
    candle0 = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    advance_paper_trading(engine_config, candle0, make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110))
    t1 = T0 + timedelta(hours=1)
    candle1 = make_candle(symbol, t1, open=101, high=101, low=101, close=101)
    advance_paper_trading(engine_config, candle1, make_signal(symbol, t1, "WAIT"))
    assert PaperPosition.objects.filter(status=PaperPosition.Status.OPEN).count() == 1

    account = get_paper_account()
    account.paused = True
    account.save()

    t2 = t1 + timedelta(hours=1)
    candle2 = make_candle(symbol, t2, open=100, high=100, low=90, close=94)  # still hits SL while paused
    advance_paper_trading(engine_config, candle2, make_signal(symbol, t2, "WAIT"))

    assert PaperPosition.objects.count() == 1  # not deleted
    assert PaperPosition.objects.get().status == PaperPosition.Status.CLOSED  # still monitored while paused
    assert PaperTrade.objects.count() == 1  # historical result preserved


@pytest.mark.django_db
def test_disabled_execution_mode_never_touches_paper_trading(symbol):
    engine_config = EngineConfig.objects.create(execution_mode=EngineConfig.ExecutionMode.DISABLED, timeframe="1h")
    candle = make_candle(symbol, T0, open=100, high=100, low=100, close=100)
    signal = make_signal(symbol, T0, "LONG", stop_loss=95, take_profit=110)

    advance_paper_trading(engine_config, candle, signal)

    assert PaperPosition.objects.count() == 0
