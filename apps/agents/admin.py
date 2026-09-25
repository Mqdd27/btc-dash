from django.contrib import admin

from .models import AgentDecision


@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ("signal", "model", "decision", "confidence", "cached", "estimated_cost", "created_at")
    list_filter = ("model", "decision", "cached")
