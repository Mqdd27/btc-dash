"""Business logic for the trading app, kept out of views/admin."""

from django.utils import timezone

from apps.ml.prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD
from apps.strategy.models import StrategyConfig
from core.execution.scheduling import next_candle_close

from .models import EngineConfig, LiveSignal, PaperPosition, PaperTrade
from .paper import get_paper_account, unrealized_pnl

RECENT_SIGNAL_HISTORY_LIMIT = 20


def get_engine_config() -> EngineConfig:
    """Single row holding the live engine state; created with safe defaults on first use."""
    config, _ = EngineConfig.objects.get_or_create(pk=1)
    return config


def describe_signal_reason(signal: LiveSignal) -> str:
    """Human-readable explanation of why a LiveSignal ended up LONG/SHORT/WAIT --
    derived entirely from fields already on the signal/feature snapshot/AI
    review rows, no extra storage needed."""
    snapshot = signal.feature_snapshot

    if signal.baseline_side == LiveSignal.Side.WAIT:
        config = StrategyConfig.objects.filter(timeframe=signal.timeframe).first()
        ema_fast = getattr(snapshot, f"ema_{config.ema_fast}", None) if config else None
        ema_slow = getattr(snapshot, f"ema_{config.ema_slow}", None) if config else None
        if config and snapshot.rsi_14 is not None and ema_fast is not None and ema_slow is not None:
            trend = f"EMA{config.ema_fast} {'>' if ema_fast > ema_slow else '<'} EMA{config.ema_slow}"
            return (
                f"Baseline strategy: {trend}, RSI {snapshot.rsi_14:.1f} "
                f"(needs > {config.rsi_long_threshold:.0f} for LONG, < {config.rsi_short_threshold:.0f} for SHORT) "
                "-- trend/RSI didn't align, so no candidate."
            )
        return "Indicators not warmed up yet for this candle."

    if signal.decision == LiveSignal.Side.WAIT:  # baseline fired but got filtered out downstream
        pipeline = getattr(signal, "agent_pipeline_run", None)
        review = getattr(signal, "agent_decision", None)
        if pipeline is not None:
            risk_step = pipeline.steps.filter(agent_name="risk_reviewer").first()
            trader_step = pipeline.steps.filter(agent_name="trader").first()
            if risk_step and not risk_step.output.get("approved", True):
                return f"TradingAgents: baseline {signal.baseline_side} rejected by Risk Reviewer -- {risk_step.output.get('reason', '')}"
            if trader_step:
                return f"TradingAgents: Trader called {trader_step.output.get('decision')} -- {trader_step.output.get('reasoning', '')}"
        if review is not None:
            return (
                f"AI reviewer: baseline {signal.baseline_side} skipped -- "
                f"{review.reason} (confidence {review.confidence:.2f})"
            )
        if signal.model_probability is not None:
            return (
                f"Baseline {signal.baseline_side}, but XGBoost win probability {signal.model_probability:.2f} "
                f"was below the {DEFAULT_WIN_PROBABILITY_THRESHOLD:.2f} threshold."
            )
        return f"Baseline {signal.baseline_side}, but no active ML model yet to confirm it -- staying WAIT."

    parts = [f"Baseline {signal.decision} confirmed"]
    if signal.model_probability is not None:
        parts.append(f"XGBoost P(win)={signal.model_probability:.2f}")
    pipeline = getattr(signal, "agent_pipeline_run", None)
    review = getattr(signal, "agent_decision", None)
    if pipeline is not None:
        parts.append("approved by TradingAgents")
    elif review is not None:
        parts.append(f"approved by AI reviewer ({review.reason})")
    return ", ".join(parts) + "."


def get_live_engine_stats(engine: EngineConfig) -> dict:
    signals = list(
        LiveSignal.objects.filter(timeframe=engine.timeframe)
        .select_related("feature_snapshot", "agent_decision", "agent_pipeline_run")
        .order_by("-timestamp")[:RECENT_SIGNAL_HISTORY_LIMIT]
    )
    last_signal = signals[0] if signals else None
    return {
        "last_signal": last_signal,
        "last_signal_reason": describe_signal_reason(last_signal) if last_signal else None,
        "last_evaluation_at": last_signal.created_at if last_signal else None,
        "next_expected_candle": next_candle_close(timezone.now(), engine.timeframe) if engine.enabled else None,
        "daily_inference_count": LiveSignal.objects.filter(
            timeframe=engine.timeframe, created_at__date=timezone.now().date(), model_probability__isnull=False,
        ).count(),
        "recent_signals": [{"signal": s, "reason": describe_signal_reason(s)} for s in signals],
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
