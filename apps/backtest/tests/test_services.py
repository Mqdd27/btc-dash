from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from apps.backtest.models import BacktestRun, BacktestTrade
from apps.backtest.services import get_chart_data, run_backtest
from apps.market.models import Candle, FeatureSnapshot, MarketSymbol
from apps.strategy.models import StrategyConfig

START = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def strategy_config(db):
    return StrategyConfig.objects.create(name="ema_rsi", timeframe="1h")


def seed_data(symbol, n=10):
    """A few candles with a feature snapshot that triggers a LONG signal midway."""
    for i in range(n):
        ts = START + timedelta(hours=i)
        price = 100 + i
        Candle.objects.create(
            symbol=symbol, timeframe="1h", timestamp=ts,
            open=price, high=price + 2, low=price - 2, close=price, volume=1, closed=True,
        )
        FeatureSnapshot.objects.create(
            symbol=symbol, timeframe="1h", timestamp=ts,
            ema_20=110, ema_50=100, rsi_14=60, atr_14=2.0,  # LONG on every candle
        )
    return START, START + timedelta(hours=n - 1)


@pytest.mark.django_db
def test_run_backtest_persists_run_and_trades(symbol, strategy_config):
    start, end = seed_data(symbol)

    backtest = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)

    assert backtest.status == BacktestRun.Status.COMPLETED
    assert backtest.metrics is not None
    assert "benchmark" in backtest.metrics
    assert BacktestTrade.objects.filter(backtest=backtest).count() == backtest.metrics["total_trades"]


@pytest.mark.django_db
def test_run_backtest_is_deterministic(symbol, strategy_config):
    start, end = seed_data(symbol)

    first = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)
    second = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)

    assert first.metrics["total_trades"] == second.metrics["total_trades"]
    assert first.metrics["final_capital"] == second.metrics["final_capital"]
    assert first.metrics["max_drawdown_pct"] == second.metrics["max_drawdown_pct"]


@pytest.mark.django_db
def test_get_chart_data_has_one_marker_pair_per_closed_trade(symbol, strategy_config):
    start, end = seed_data(symbol)
    backtest = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)

    chart_data = get_chart_data(backtest)

    closed_trades = backtest.trades.filter(exit_timestamp__isnull=False).count()
    assert len(chart_data["markers"]) == closed_trades * 2
    assert len(chart_data["equity_curve"]) == closed_trades
    assert len(chart_data["price_series"]) == Candle.objects.filter(symbol=symbol, timeframe="1h").count()
    # markers must be chronologically sorted for the chart library
    times = [m["time"] for m in chart_data["markers"]]
    assert times == sorted(times)
