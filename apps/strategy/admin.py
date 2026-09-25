from django.contrib import admin

from .models import SignalCandidate, StrategyConfig


@admin.register(StrategyConfig)
class StrategyConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "timeframe", "ema_fast", "ema_slow", "updated_at")


@admin.register(SignalCandidate)
class SignalCandidateAdmin(admin.ModelAdmin):
    list_display = ("strategy", "symbol", "timeframe", "candle_timestamp", "side", "entry_reference_price")
    list_filter = ("strategy", "symbol", "timeframe", "side")
