from django.contrib import admin

from .models import EngineConfig


@admin.register(EngineConfig)
class EngineConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "enabled", "mode", "timeframe", "execution_mode", "updated_at")
