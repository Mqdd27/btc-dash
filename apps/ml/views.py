from django.shortcuts import get_object_or_404, render

from .models import WalkForwardRun


def walk_forward_list_view(request):
    runs = WalkForwardRun.objects.select_related("strategy", "symbol").order_by("-created_at")
    return render(request, "ml/walk_forward_list.html", {"runs": runs})


def walk_forward_detail_view(request, pk):
    run = get_object_or_404(WalkForwardRun.objects.select_related("strategy", "symbol"), pk=pk)
    windows = run.windows.all()
    return render(request, "ml/walk_forward_detail.html", {"run": run, "windows": windows})
