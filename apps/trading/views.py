from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import EngineConfig
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
        if mode in EngineConfig.Mode.values:
            engine.mode = mode
        if timeframe in EngineConfig.Timeframe.values:
            engine.timeframe = timeframe

    engine.save()
    return redirect("dashboard")
