from django.conf import settings
from django.utils import timezone

from .models import AgentDecision, AgentPipelineRun, AgentStepDecision


def get_ai_reviewer_stats() -> dict:
    """Combines both AI paths -- the single reviewer (quant_ai) and the
    TradingAgents pipeline (full_agent) -- since they share one daily budget
    and the dashboard has one AI card, not two."""
    today = timezone.now().date()
    decisions_today = AgentDecision.objects.filter(created_at__date=today)
    steps_today = AgentStepDecision.objects.filter(created_at__date=today)
    real_decisions = decisions_today.filter(cached=False)
    real_steps = steps_today.filter(cached=False)

    last_decision = AgentDecision.objects.order_by("-created_at").first()
    last_pipeline_run = AgentPipelineRun.objects.order_by("-created_at").first()

    return {
        "ai_enabled": settings.AI_ENABLED,
        "calls_today": real_decisions.count() + real_steps.count(),
        "daily_call_limit": settings.AI_DAILY_CALL_LIMIT,
        "input_tokens_today": (
            sum(d.input_tokens for d in real_decisions) + sum(s.input_tokens for s in real_steps)
        ),
        "output_tokens_today": (
            sum(d.output_tokens for d in real_decisions) + sum(s.output_tokens for s in real_steps)
        ),
        "cache_hits_today": decisions_today.filter(cached=True).count() + steps_today.filter(cached=True).count(),
        "estimated_cost_today": (
            sum(d.estimated_cost or 0 for d in real_decisions) + sum(s.estimated_cost or 0 for s in real_steps)
        ),
        "last_decision": last_decision,
        "last_pipeline_run": last_pipeline_run,
        "min_quant_probability": settings.AI_MIN_QUANT_PROBABILITY,
    }
