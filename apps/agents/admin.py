from django.contrib import admin

from .models import AgentDecision, AgentPipelineRun, AgentStepDecision


@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ("signal", "model", "decision", "confidence", "cached", "estimated_cost", "created_at")
    list_filter = ("model", "decision", "cached")


@admin.register(AgentPipelineRun)
class AgentPipelineRunAdmin(admin.ModelAdmin):
    list_display = ("signal", "final_recommendation", "total_input_tokens", "total_output_tokens", "total_estimated_cost", "created_at")
    list_filter = ("final_recommendation",)


@admin.register(AgentStepDecision)
class AgentStepDecisionAdmin(admin.ModelAdmin):
    list_display = ("pipeline_run", "agent_name", "model", "cached", "estimated_cost", "created_at")
    list_filter = ("agent_name", "model", "cached")
