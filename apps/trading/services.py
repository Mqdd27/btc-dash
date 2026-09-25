"""Business logic for the trading app, kept out of views/admin."""

from .models import EngineConfig


def get_engine_config() -> EngineConfig:
    """Single row holding the live engine state; created with safe defaults on first use."""
    config, _ = EngineConfig.objects.get_or_create(pk=1)
    return config
