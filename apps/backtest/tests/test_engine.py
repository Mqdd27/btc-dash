from datetime import datetime, timedelta, timezone as dt_timezone

from core.quant.backtest import BacktestEngineConfig, CandleBar, SignalInput, run_engine

T0 = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


def bar(hours, open, high, low, close):
    return CandleBar(timestamp=T0 + timedelta(hours=hours), open=open, high=high, low=low, close=close)


def cfg(**overrides):
    base = dict(
        initial_capital=10000, position_size_type="fixed_cash", risk_per_trade=100,
        maker_fee=0, taker_fee=0, slippage_percent=0, allow_long=True, allow_short=True,
        maximum_simultaneous_positions=1,
    )
    base.update(overrides)
    return BacktestEngineConfig(**base)


def test_long_trade_take_profit():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 101, 105, 100, 104), bar(2, 104, 110, 103, 108)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=110)]

    trades, _ = run_engine(candles, signals, cfg())

    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == "LONG"
    assert trade.exit_reason == "take_profit"
    assert trade.entry_price == 101  # next candle's open, not the signal candle's
    assert trade.exit_price == 110
    size = 100 / (101 - 95)
    assert trade.size == size
    assert trade.gross_pnl == (110 - 101) * size
    assert trade.net_pnl == trade.gross_pnl  # zero fees in this config


def test_short_trade_take_profit():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 99, 100, 90, 92), bar(2, 92, 93, 85, 88)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="SHORT", stop_loss=105, take_profit=85)]

    trades, _ = run_engine(candles, signals, cfg())

    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == "SHORT"
    assert trade.exit_reason == "take_profit"
    assert trade.entry_price == 99
    assert trade.exit_price == 85
    size = 100 / (105 - 99)
    assert trade.net_pnl == (99 - 85) * size


def test_stop_loss_hit():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 101, 102, 94, 95), bar(2, 95, 96, 90, 91)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=120)]

    trades, _ = run_engine(candles, signals, cfg())

    assert trades[0].exit_reason == "stop_loss"
    assert trades[0].exit_price == 95


def test_fees_are_charged_on_entry_and_exit():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100), bar(2, 100, 110, 90, 100)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=105)]

    trades, _ = run_engine(candles, signals, cfg(taker_fee=0.001))

    trade = trades[0]
    size = 100 / (100 - 95)
    expected_fee = (trade.entry_price * size * 0.001) + (trade.exit_price * size * 0.001)
    assert trade.fees == expected_fee
    assert trade.net_pnl == trade.gross_pnl - expected_fee


def test_slippage_moves_fills_against_the_trader():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100), bar(2, 100, 110, 97, 100)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=105)]

    trades, _ = run_engine(candles, signals, cfg(slippage_percent=0.01))

    trade = trades[0]
    assert trade.entry_price == 100 * 1.01  # buy fill marked up
    assert trade.exit_price == 105 * 0.99  # sell-to-close fill marked down
    assert trade.slippage > 0


def test_signal_executes_no_earlier_than_next_candle_open():
    # If entry happened on the signal's own candle, this SL would already be hit
    # intrabar. It must not be -- entry only happens at the next candle's open.
    candles = [
        bar(0, 100, 100, 50, 100),  # signal candle: huge range, would trip SL if entered here
        bar(1, 100, 101, 99, 100),
        bar(2, 100, 105, 99, 100),
    ]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=110)]

    trades, _ = run_engine(candles, signals, cfg())

    assert len(trades) == 1
    assert trades[0].entry_timestamp == candles[1].timestamp
    assert trades[0].entry_price == candles[1].open
    assert trades[0].exit_reason == "end_of_data"  # SL/TP never touched after entry


def test_same_candle_sl_tp_collision_assumes_stop_loss_first():
    candles = [
        bar(0, 100, 100, 100, 100),
        bar(1, 100, 100, 100, 100),  # entry candle
        bar(2, 100, 130, 80, 100),  # both SL (95) and TP (110) are inside this range
    ]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=110)]

    trades, _ = run_engine(candles, signals, cfg())

    assert trades[0].exit_reason == "stop_loss"  # conservative assumption, never the profitable one


def test_equity_curve_has_one_point_per_candle_and_reflects_realized_pnl():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100), bar(2, 100, 110, 90, 100)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=105)]

    trades, equity_curve = run_engine(candles, signals, cfg())

    assert len(equity_curve) == len(candles)
    assert equity_curve[-1].equity == trades[-1].equity_after


def test_later_candles_do_not_affect_already_closed_trades():
    candles = [bar(0, 100, 100, 100, 100), bar(1, 100, 100, 100, 100), bar(2, 100, 110, 90, 100)]
    signals = [SignalInput(timestamp=candles[0].timestamp, side="LONG", stop_loss=95, take_profit=105)]

    trades_before, _ = run_engine(candles, signals, cfg())

    extra_candles = candles + [bar(3, 1, 999999, 0.01, 1)]  # wild future candle
    trades_after, _ = run_engine(extra_candles, signals, cfg())

    assert trades_before[0] == trades_after[0]
