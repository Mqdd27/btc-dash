import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig

from .models import EngineConfig
from .paper import get_paper_account
from .services import get_engine_config
from .engine import evaluate_now
from .tasks import DEFAULT_STRATEGY_NAME, DEFAULT_SYMBOL

logger = logging.getLogger(__name__)


@require_POST
def update_engine_view(request):
    """Explicit action names (not a generic "save"), so a single misclick
    can't silently flip the enabled toggle -- each button means one thing."""
    engine = get_engine_config()
    action = request.POST.get("action")

    if action == "enable":
        engine.enabled = True
    elif action == "disable":
        engine.enabled = False
    elif action == "save_config":
        mode = request.POST.get("mode")
        timeframe = request.POST.get("timeframe")
        execution_mode = request.POST.get("execution_mode")
        if mode in EngineConfig.Mode.values:
            engine.mode = mode
        if timeframe in EngineConfig.Timeframe.values:
            engine.timeframe = timeframe
        # "live" is deliberately never accepted here -- no UI path can turn on
        # real order execution, since it doesn't exist. See apps/trading/paper.py.
        if execution_mode in (EngineConfig.ExecutionMode.DISABLED, EngineConfig.ExecutionMode.PAPER):
            engine.execution_mode = execution_mode

    engine.save()
    return redirect("dashboard")


@require_POST
def update_paper_trading_view(request):
    """Pause/resume only -- never deletes PaperPosition/PaperTrade rows."""
    account = get_paper_account()
    action = request.POST.get("action")

    if action == "pause":
        account.paused = True
    elif action == "resume":
        account.paused = False

    account.save(update_fields=["paused"])
    return redirect("dashboard")


@require_POST
def evaluate_past_view(request):
    """Catch-up for a candle missed while the engine wasn't running: quant
    signal only. Deliberately no AI review (real API cost) and no paper
    trading (fills assume candles arrive in order)."""
    at = parse_datetime(request.POST.get("at", ""))
    if at is None:
        messages.error(request, "Invalid date/time.")
        return redirect("dashboard")
    if timezone.is_naive(at):
        at = timezone.make_aware(at)  # datetime-local input = TIME_ZONE (Asia/Jakarta)
    if at > timezone.now():
        messages.error(request, "That time is in the future.")
        return redirect("dashboard")

    engine = get_engine_config()
    strategy_config, _ = StrategyConfig.objects.get_or_create(
        name=DEFAULT_STRATEGY_NAME, defaults={"timeframe": engine.timeframe}
    )
    try:
        signal = evaluate_now(strategy_config, resolve_market_symbol(DEFAULT_SYMBOL), engine.timeframe, at=at)
    except Exception as exc:  # network/exchange errors -- show them instead of a 500 page
        logger.exception("evaluate_past failed")
        messages.error(request, f"Failed to get signal: {exc}")
        return redirect("dashboard")

    if signal is None:
        messages.warning(request, "No new signal: that candle was already evaluated, or its data/features aren't available.")
    else:
        local_ts = timezone.localtime(signal.timestamp).strftime("%Y-%m-%d %H:%M")
        messages.success(request, f"Signal for {engine.timeframe} candle @ {local_ts} WIB: {signal.decision}")
    return redirect("dashboard")
