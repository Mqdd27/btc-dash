"""Backtest performance metrics. Pure functions over trades/candles -- no DB."""

import statistics

from .backtest import CandleBar, Trade


def compute_metrics(trades: list[Trade], initial_capital: float) -> dict:
    final_capital = trades[-1].equity_after if trades else initial_capital
    total_return_pct = (final_capital - initial_capital) / initial_capital * 100 if initial_capital else 0.0

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = sum(t.net_pnl for t in losses)  # negative or zero

    metrics = {
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return_pct": total_return_pct,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": (len(wins) / len(trades) * 100) if trades else 0.0,
        "average_win": statistics.mean(t.net_pnl for t in wins) if wins else 0.0,
        "average_loss": statistics.mean(t.net_pnl for t in losses) if losses else 0.0,
        "expectancy": statistics.mean(t.net_pnl for t in trades) if trades else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss else None,
        "max_drawdown_pct": _max_drawdown_pct(trades, initial_capital),
        # ponytail: trades are irregular events, not fixed-interval bars, so this
        # is an unannualized per-trade Sharpe/Sortino (mean/std of trade returns),
        # not a calendar-annualized one. Upgrade to daily-resampled equity if a
        # like-for-like comparison across timeframes is ever needed.
        "sharpe_ratio": _sharpe(trades),
        "sortino_ratio": _sortino(trades),
        "average_trade_duration_hours": _avg_duration_hours(trades),
        "max_consecutive_wins": _max_consecutive(trades, wins=True),
        "max_consecutive_losses": _max_consecutive(trades, wins=False),
    }
    return metrics


def _max_drawdown_pct(trades: list[Trade], initial_capital: float) -> float:
    peak = initial_capital
    max_dd = 0.0
    for t in trades:
        peak = max(peak, t.equity_after)
        if peak > 0:
            max_dd = max(max_dd, (peak - t.equity_after) / peak * 100)
    return max_dd


def _sharpe(trades: list[Trade]) -> float | None:
    returns = [t.return_pct for t in trades]
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    return (statistics.mean(returns) / stdev) if stdev else None


def _sortino(trades: list[Trade]) -> float | None:
    returns = [t.return_pct for t in trades]
    downside = [r for r in returns if r < 0]
    if len(returns) < 2 or len(downside) < 2:
        return None
    downside_std = statistics.stdev(downside)
    return (statistics.mean(returns) / downside_std) if downside_std else None


def _avg_duration_hours(trades: list[Trade]) -> float | None:
    durations = [
        (t.exit_timestamp - t.entry_timestamp).total_seconds() / 3600
        for t in trades
        if t.exit_timestamp is not None
    ]
    return statistics.mean(durations) if durations else None


def _max_consecutive(trades: list[Trade], wins: bool) -> int:
    best = current = 0
    for t in trades:
        is_match = (t.net_pnl > 0) if wins else (t.net_pnl < 0)
        current = current + 1 if is_match else 0
        best = max(best, current)
    return best


def compute_buy_hold(candles: list[CandleBar], initial_capital: float) -> dict:
    """Naive buy-at-first-open, hold-to-last-close benchmark. No fees/slippage --
    it's a reference point, not a simulated trade."""
    if not candles:
        return {"final_capital": initial_capital, "total_return_pct": 0.0}

    entry_price = candles[0].open
    exit_price = candles[-1].close
    final_capital = initial_capital * (exit_price / entry_price)
    return {
        "final_capital": final_capital,
        "total_return_pct": (final_capital - initial_capital) / initial_capital * 100,
    }
