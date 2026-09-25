from django.conf import settings
from django.utils import timezone

from .models import AgentDecision


def get_ai_reviewer_stats() -> dict:
    today = AgentDecision.objects.filter(created_at__date=timezone.now().date())
    real_calls = today.filter(cached=False)
    last_decision = AgentDecision.objects.order_by("-created_at").first()

    return {
        "ai_enabled": settings.AI_ENABLED,
        "calls_today": real_calls.count(),
        "daily_call_limit": settings.AI_DAILY_CALL_LIMIT,
        "input_tokens_today": sum(d.input_tokens for d in real_calls),
        "output_tokens_today": sum(d.output_tokens for d in real_calls),
        "cache_hits_today": today.filter(cached=True).count(),
        "estimated_cost_today": sum(d.estimated_cost or 0 for d in real_calls),
        "last_decision": last_decision,
    }
