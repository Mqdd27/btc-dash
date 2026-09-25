"""Orchestration: load candles + signals, run the engine, persist the results."""

from django.utils import timezone

from apps.market.models import Candle, MarketSymbol
from apps.strategy.models import SignalCandidate, StrategyConfig
from apps.strategy.services import generate_signals
from core.quant.backtest import BacktestEngineConfig, CandleBar, SignalInput, run_engine
from core.quant.metrics import compute_buy_hold, compute_metrics

from .models import BacktestRun, BacktestTrade

DEFAULT_ENGINE_CONFIG = {
    "position_size_type": "percentage_of_equity",
    "risk_per_trade": 0.01,
    "maker_fee": 0.0002,
    "taker_fee": 0.0004,
    "slippage_percent": 0.0005,
    "allow_long": True,
    "allow_short": True,
    "maximum_simultaneous_positions": 1,
}


def run_backtest(
    strategy_config: StrategyConfig,
    symbol: MarketSymbol,
    timeframe: str,
    start,
    end,
    initial_capital: float,
    engine_overrides: dict | None = None,
) -> BacktestRun:
    generate_signals(strategy_config, symbol, timeframe, start, end)  # idempotent

    candles = [
        CandleBar(timestamp=row["timestamp"], open=float(row["open"]), high=float(row["high"]),
                   low=float(row["low"]), close=float(row["close"]))
        for row in Candle.objects.filter(
            symbol=symbol, timeframe=timeframe, closed=True, timestamp__gte=start, timestamp__lte=end
        ).order_by("timestamp").values("timestamp", "open", "high", "low", "close")
    ]
    signals = [
        SignalInput(
            timestamp=row["candle_timestamp"], side=row["side"],
            stop_loss=row["stop_loss_reference"], take_profit=row["take_profit_reference"],
        )
        for row in SignalCandidate.objects.filter(
            strategy=strategy_config, symbol=symbol, timeframe=timeframe,
            candle_timestamp__gte=start, candle_timestamp__lte=end,
        ).values("candle_timestamp", "side", "stop_loss_reference", "take_profit_reference")
    ]

    config_dict = {**DEFAULT_ENGINE_CONFIG, **(engine_overrides or {}), "initial_capital": initial_capital}
    engine_config = BacktestEngineConfig(**config_dict)

    backtest = BacktestRun.objects.create(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe,
        start_date=start, end_date=end, configuration=config_dict,
        initial_capital=initial_capital, status=BacktestRun.Status.RUNNING,
    )

    trades, _equity_curve = run_engine(candles, signals, engine_config)
    metrics = compute_metrics(trades, initial_capital)
    metrics["benchmark"] = compute_buy_hold(candles, initial_capital)

    BacktestTrade.objects.bulk_create(
        [
            BacktestTrade(
                backtest=backtest, side=t.side, signal_timestamp=t.signal_timestamp,
                entry_timestamp=t.entry_timestamp, entry_price=t.entry_price,
                exit_timestamp=t.exit_timestamp, exit_price=t.exit_price,
                stop_loss=t.stop_loss, take_profit=t.take_profit, size=t.size,
                fees=t.fees, slippage=t.slippage, gross_pnl=t.gross_pnl, net_pnl=t.net_pnl,
                return_pct=t.return_pct, exit_reason=t.exit_reason, equity_after=t.equity_after,
            )
            for t in trades
        ]
    )

    backtest.final_capital = metrics["final_capital"]
    backtest.metrics = metrics
    backtest.status = BacktestRun.Status.COMPLETED
    backtest.completed_at = timezone.now()
    backtest.save(update_fields=["final_capital", "metrics", "status", "completed_at"])
    return backtest
