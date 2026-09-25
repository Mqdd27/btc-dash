from django.contrib import admin

from .models import EngineConfig, LiveSignal


@admin.register(EngineConfig)
class EngineConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "enabled", "mode", "timeframe", "execution_mode", "updated_at")


@admin.register(LiveSignal)
class LiveSignalAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timeframe", "timestamp", "baseline_side", "decision", "model_probability")
    list_filter = ("symbol", "timeframe", "decision")
