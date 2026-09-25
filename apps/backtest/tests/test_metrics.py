from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from core.quant.backtest import CandleBar, Trade
from core.quant.metrics import compute_buy_hold, compute_metrics

T0 = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


def trade(net_pnl, equity_after, **overrides):
    kwargs = dict(
        side="LONG", signal_timestamp=T0, entry_timestamp=T0, entry_price=100,
        stop_loss=95, take_profit=105, size=1, exit_timestamp=T0 + timedelta(hours=1),
        exit_price=100 + net_pnl, exit_reason="take_profit", fees=0, slippage=0,
        gross_pnl=net_pnl, net_pnl=net_pnl, return_pct=net_pnl, equity_after=equity_after,
    )
    kwargs.update(overrides)
    return Trade(**kwargs)


def test_profit_factor():
    trades = [trade(100, 1100), trade(-50, 1050), trade(200, 1250), trade(-25, 1225)]

    metrics = compute_metrics(trades, initial_capital=1000)

    assert metrics["gross_profit"] == 300
    assert metrics["gross_loss"] == -75
    assert metrics["profit_factor"] == 300 / 75


def test_max_drawdown():
    trades = [trade(100, 1100), trade(-50, 1050), trade(150, 1200), trade(-300, 900)]

    metrics = compute_metrics(trades, initial_capital=1000)

    assert metrics["max_drawdown_pct"] == (1200 - 900) / 1200 * 100


def test_win_rate_and_counts():
    trades = [trade(10, 1010), trade(-5, 1005), trade(20, 1025)]

    metrics = compute_metrics(trades, initial_capital=1000)

    assert metrics["total_trades"] == 3
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["win_rate_pct"] == pytest.approx(200 / 3)


def test_no_trades_is_flat():
    metrics = compute_metrics([], initial_capital=1000)

    assert metrics["final_capital"] == 1000
    assert metrics["total_return_pct"] == 0
    assert metrics["profit_factor"] is None


def test_buy_hold_benchmark():
    candles = [
        CandleBar(timestamp=T0, open=100, high=100, low=100, close=100),
        CandleBar(timestamp=T0 + timedelta(hours=1), open=100, high=120, low=90, close=110),
    ]

    result = compute_buy_hold(candles, initial_capital=1000)

    assert result["final_capital"] == 1000 * (110 / 100)
    assert result["total_return_pct"] == 10.0
