"""Business logic for the trading app, kept out of views/admin."""

from django.utils import timezone

from core.execution.scheduling import next_candle_close

from .models import EngineConfig, LiveSignal


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
