from django.shortcuts import get_object_or_404, render

from .models import AgentPipelineRun

STEP_ORDER = [
    "technical_analyst", "derivatives_analyst", "sentiment_analyst",
    "bull_researcher", "bear_researcher", "trader", "risk_reviewer",
]


def pipeline_list_view(request):
    runs = AgentPipelineRun.objects.select_related(
        "signal", "signal__symbol"
    ).order_by("-created_at")
    return render(request, "agents/pipeline_list.html", {"runs": runs})


def pipeline_detail_view(request, pk):
    run = get_object_or_404(
        AgentPipelineRun.objects.select_related("signal", "signal__symbol", "signal__model_version"), pk=pk
    )
    steps_by_name = {s.agent_name: s for s in run.steps.all()}
    ordered_steps = [steps_by_name[name] for name in STEP_ORDER if name in steps_by_name]
    return render(request, "agents/pipeline_detail.html", {"run": run, "steps": ordered_steps})
