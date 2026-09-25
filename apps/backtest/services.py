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


def create_backtest_run(
    strategy_config: StrategyConfig,
    symbol: MarketSymbol,
    timeframe: str,
    start,
    end,
    initial_capital: float,
    engine_overrides: dict | None = None,
) -> BacktestRun:
    """Fast, HTTP-request-safe: just persists the run request as queued. The
    actual simulation happens in execute_backtest(), called from a Celery task."""
    config_dict = {**DEFAULT_ENGINE_CONFIG, **(engine_overrides or {}), "initial_capital": initial_capital}
    return BacktestRun.objects.create(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe,
        start_date=start, end_date=end, configuration=config_dict,
        initial_capital=initial_capital, status=BacktestRun.Status.QUEUED,
    )


def load_candle_bars(symbol: MarketSymbol, timeframe: str, start, end) -> list[CandleBar]:
    return [
        CandleBar(timestamp=row["timestamp"], open=float(row["open"]), high=float(row["high"]),
                   low=float(row["low"]), close=float(row["close"]))
        for row in Candle.objects.filter(
            symbol=symbol, timeframe=timeframe, closed=True, timestamp__gte=start, timestamp__lte=end,
        ).order_by("timestamp").values("timestamp", "open", "high", "low", "close")
    ]


def load_signal_inputs(
    strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, start, end
) -> list[SignalInput]:
    return [
        SignalInput(
            timestamp=row["candle_timestamp"], side=row["side"],
            stop_loss=row["stop_loss_reference"], take_profit=row["take_profit_reference"],
        )
        for row in SignalCandidate.objects.filter(
            strategy=strategy_config, symbol=symbol, timeframe=timeframe,
            candle_timestamp__gte=start, candle_timestamp__lte=end,
        ).values("candle_timestamp", "side", "stop_loss_reference", "take_profit_reference")
    ]


def execute_backtest(backtest: BacktestRun) -> BacktestRun:
    """The actual simulation work. Safe to call directly (CLI/tests) or from a
    Celery task -- this function itself has no opinion on how it's invoked."""
    backtest.status = BacktestRun.Status.RUNNING
    backtest.save(update_fields=["status"])

    try:
        generate_signals(
            backtest.strategy, backtest.symbol, backtest.timeframe, backtest.start_date, backtest.end_date
        )  # idempotent

        candles = load_candle_bars(backtest.symbol, backtest.timeframe, backtest.start_date, backtest.end_date)
        signals = load_signal_inputs(
            backtest.strategy, backtest.symbol, backtest.timeframe, backtest.start_date, backtest.end_date
        )

        engine_config = BacktestEngineConfig(**backtest.configuration)
        trades, _equity_curve = run_engine(candles, signals, engine_config)
        metrics = compute_metrics(trades, backtest.initial_capital)
        metrics["benchmark"] = compute_buy_hold(candles, backtest.initial_capital)

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
    except Exception as exc:
        backtest.status = BacktestRun.Status.FAILED
        backtest.metrics = {"error": str(exc)}
        backtest.completed_at = timezone.now()
        backtest.save(update_fields=["status", "metrics", "completed_at"])
        raise

    return backtest


def run_backtest(
    strategy_config: StrategyConfig,
    symbol: MarketSymbol,
    timeframe: str,
    start,
    end,
    initial_capital: float,
    engine_overrides: dict | None = None,
) -> BacktestRun:
    """Synchronous convenience wrapper (CLI, tests): create + execute inline,
    no Celery involved. The web UI uses create_backtest_run + the Celery task
    instead, since a request must never block on the simulation."""
    backtest = create_backtest_run(
        strategy_config, symbol, timeframe, start, end, initial_capital, engine_overrides
    )
    return execute_backtest(backtest)


def get_chart_data(backtest: BacktestRun) -> dict:
    """Everything the detail page's charts need, derived from stored trades/candles
    -- no separate per-candle equity series is persisted; equity only changes on
    trade close (see core/quant/backtest.py), so trades are the full story."""
    trades = list(backtest.trades.order_by("exit_timestamp"))

    equity = backtest.initial_capital
    peak = backtest.initial_capital
    cumulative_pnl = 0.0
    equity_curve, drawdown_curve, pnl_curve = [], [], []
    for t in trades:
        if t.exit_timestamp is None:
            continue
        equity = t.equity_after
        peak = max(peak, equity)
        cumulative_pnl += t.net_pnl
        ts = int(t.exit_timestamp.timestamp())
        equity_curve.append({"time": ts, "value": equity})
        drawdown_curve.append({"time": ts, "value": -(peak - equity) / peak * 100 if peak else 0})
        pnl_curve.append({"time": ts, "value": cumulative_pnl})

    candles = list(
        Candle.objects.filter(
            symbol=backtest.symbol, timeframe=backtest.timeframe, closed=True,
            timestamp__gte=backtest.start_date, timestamp__lte=backtest.end_date,
        ).order_by("timestamp").values("timestamp", "open", "high", "low", "close")
    )
    price_series = [
        {"time": int(row["timestamp"].timestamp()), "open": float(row["open"]), "high": float(row["high"]),
         "low": float(row["low"]), "close": float(row["close"])}
        for row in candles
    ]
    markers = []
    for t in trades:
        markers.append({
            "time": int(t.entry_timestamp.timestamp()), "position": "belowBar" if t.side == "LONG" else "aboveBar",
            "color": "#16a34a" if t.side == "LONG" else "#dc2626",
            "shape": "arrowUp" if t.side == "LONG" else "arrowDown", "text": f"{t.side} entry",
        })
        if t.exit_timestamp is not None:
            markers.append({
                "time": int(t.exit_timestamp.timestamp()), "position": "aboveBar" if t.side == "LONG" else "belowBar",
                "color": "#16a34a" if t.net_pnl >= 0 else "#dc2626",
                "shape": "arrowDown" if t.side == "LONG" else "arrowUp", "text": f"exit ({t.exit_reason})",
            })
    markers.sort(key=lambda m: m["time"])

    return {
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "pnl_curve": pnl_curve,
        "price_series": price_series,
        "markers": markers,
    }
