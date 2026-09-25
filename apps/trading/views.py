from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import EngineConfig
from .paper import get_paper_account
from .services import get_engine_config


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
