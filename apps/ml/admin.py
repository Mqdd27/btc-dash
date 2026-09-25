from django.contrib import admin

from .models import ModelVersion, WalkForwardRun, WalkForwardWindow


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "algorithm", "strategy", "symbol", "timeframe", "active", "created_at")
    list_filter = ("strategy", "symbol", "timeframe", "active")


@admin.register(WalkForwardRun)
class WalkForwardRunAdmin(admin.ModelAdmin):
    list_display = ("id", "strategy", "symbol", "timeframe", "mode", "status", "start_date", "end_date")
    list_filter = ("strategy", "symbol", "timeframe", "mode", "status")


@admin.register(WalkForwardWindow)
class WalkForwardWindowAdmin(admin.ModelAdmin):
    list_display = ("run", "index", "train_start", "train_end", "test_start", "test_end")
    list_filter = ("run",)
