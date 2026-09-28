from django.http import JsonResponse
from django.shortcuts import render

from apps.agents.services import get_ai_reviewer_stats
from apps.market.features import get_feature_stats
from apps.market.services import get_symbol_stats
from apps.trading.models import LiveSignal
from apps.trading.services import get_engine_config, get_live_engine_stats, get_paper_account_stats
from core.health import celery_configured, check_database, check_redis


def dashboard_view(request):
    engine = get_engine_config()
    context = {
        "app_name": "BTC Trader",
        "db_ok": check_database(),
        "redis_ok": check_redis(),
        "celery_ok": celery_configured(),
        "engine": engine,
        "live_engine": get_live_engine_stats(engine),
        "paper": get_paper_account_stats(),
        "ai": get_ai_reviewer_stats(),
        "market_stats": get_symbol_stats("BTCUSDT", "1h"),
        "feature_stats": get_feature_stats("BTCUSDT", "1h"),
    }
    return render(request, "dashboard/index.html", context)


def live_panel_fragment_view(request):
    """Polled by htmx (see dashboard/index.html) so the current signal, signal
    history, and AI reviewer card update without a manual page reload."""
    engine = get_engine_config()
    context = {
        "engine": engine,
        "live_engine": get_live_engine_stats(engine),
        "ai": get_ai_reviewer_stats(),
    }
    return render(request, "dashboard/_live_panel_fragment.html", context)


def health_view(request):
    return JsonResponse({"status": "ok"})


def health_db_view(request):
    ok = check_database()
    return JsonResponse({"status": "ok" if ok else "error"}, status=200 if ok else 503)


def health_redis_view(request):
    ok = check_redis()
    return JsonResponse({"status": "ok" if ok else "error"}, status=200 if ok else 503)


def latest_signal_view(request):
    """Polled by the dashboard's browser-notification JS -- just the id/decision
    it needs to detect a new evaluation, nothing else."""
    engine = get_engine_config()
    signal = LiveSignal.objects.filter(timeframe=engine.timeframe).order_by("-timestamp").first()
    if signal is None:
        return JsonResponse({"id": None})
    return JsonResponse({
        "id": signal.id,
        "decision": signal.decision,
        "timestamp": signal.timestamp.isoformat(),
    })
