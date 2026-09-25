"""Business logic for the trading app, kept out of views/admin."""

from django.utils import timezone

from core.execution.scheduling import next_candle_close

from .models import EngineConfig, LiveSignal, PaperPosition, PaperTrade
from .paper import get_paper_account, unrealized_pnl


def get_engine_config() -> EngineConfig:
    """Single row holding the live engine state; created with safe defaults on first use."""
    config, _ = EngineConfig.objects.get_or_create(pk=1)
    return config


def get_live_engine_stats(engine: EngineConfig) -> dict:
    last_signal = LiveSignal.objects.filter(timeframe=engine.timeframe).order_by("-timestamp").first()
    return {
        "last_signal": last_signal,
        "last_evaluation_at": last_signal.created_at if last_signal else None,
        "next_expected_candle": next_candle_close(timezone.now(), engine.timeframe) if engine.enabled else None,
        "daily_inference_count": LiveSignal.objects.filter(
            timeframe=engine.timeframe, created_at__date=timezone.now().date(), model_probability__isnull=False,
        ).count(),
    }


def get_paper_account_stats() -> dict:
    account = get_paper_account()
    open_positions = PaperPosition.objects.filter(account=account, status=PaperPosition.Status.OPEN)
    trades = list(PaperTrade.objects.filter(position__account=account).order_by("exit_timestamp"))

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = sum(t.pnl for t in losses)

    peak = account.initial_balance
    running = account.initial_balance
    max_drawdown_pct = 0.0
    for t in trades:
        running += t.pnl
        peak = max(peak, running)
        if peak:
            max_drawdown_pct = max(max_drawdown_pct, (peak - running) / peak * 100)

    return {
        "account": account,
        "balance": account.cash_balance,
        "equity": account.equity,
        "open_positions": open_positions,
        "realized_pnl": account.cash_balance - account.initial_balance,
        "unrealized_pnl": unrealized_pnl(account),
        "total_trades": len(trades),
        "win_rate_pct": (len(wins) / len(trades) * 100) if trades else None,
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss else None,
        "max_drawdown_pct": max_drawdown_pct,
    }
