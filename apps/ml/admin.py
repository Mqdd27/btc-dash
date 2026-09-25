from django.contrib import admin

from .models import ModelVersion


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "algorithm", "strategy", "symbol", "timeframe", "active", "created_at")
    list_filter = ("strategy", "symbol", "timeframe", "active")
