from django.contrib import admin

from .models import EngineConfig, LiveSignal, PaperAccount, PaperPosition, PaperTrade


@admin.register(EngineConfig)
class EngineConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "enabled", "mode", "timeframe", "execution_mode", "updated_at")


@admin.register(LiveSignal)
class LiveSignalAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timeframe", "timestamp", "baseline_side", "decision", "model_probability")
    list_filter = ("symbol", "timeframe", "decision")


@admin.register(PaperAccount)
class PaperAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "initial_balance", "cash_balance", "equity", "paused", "updated_at")


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    list_display = ("symbol", "side", "status", "entry_timestamp", "entry_price", "stop_loss", "take_profit")
    list_filter = ("symbol", "side", "status")


@admin.register(PaperTrade)
class PaperTradeAdmin(admin.ModelAdmin):
    list_display = ("position", "exit_timestamp", "exit_price", "pnl", "return_pct", "exit_reason")
    list_filter = ("exit_reason",)
