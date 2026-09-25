from django.http import JsonResponse
from django.shortcuts import render

from apps.market.features import get_feature_stats
from apps.market.services import get_symbol_stats
from apps.trading.services import get_engine_config
from core.health import celery_configured, check_database, check_redis


def dashboard_view(request):
    context = {
        "app_name": "BTC Trader",
        "db_ok": check_database(),
        "redis_ok": check_redis(),
        "celery_ok": celery_configured(),
        "engine": get_engine_config(),
        "market_stats": get_symbol_stats("BTCUSDT", "1h"),
        "feature_stats": get_feature_stats("BTCUSDT", "1h"),
    }
    return render(request, "dashboard/index.html", context)


def health_view(request):
    return JsonResponse({"status": "ok"})


def health_db_view(request):
    ok = check_database()
    return JsonResponse({"status": "ok" if ok else "error"}, status=200 if ok else 503)


def health_redis_view(request):
    ok = check_redis()
    return JsonResponse({"status": "ok" if ok else "error"}, status=200 if ok else 503)
