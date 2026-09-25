import json
from datetime import datetime, timezone as dt_timezone

from django.shortcuts import get_object_or_404, redirect, render

from .forms import BacktestRunForm
from .models import BacktestRun, BacktestTrade
from .services import create_backtest_run, get_chart_data
from .tasks import run_backtest_task

EXIT_REASON_CHOICES = ["take_profit", "stop_loss", "end_of_data"]


def backtest_list_view(request):
    runs = BacktestRun.objects.select_related("strategy", "symbol").order_by("-created_at")
    return render(request, "backtest/list.html", {"runs": runs})


def backtest_create_view(request):
    if request.method == "POST":
        form = BacktestRunForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            start = datetime.combine(data["start_date"], datetime.min.time(), tzinfo=dt_timezone.utc)
            end = datetime.combine(data["end_date"], datetime.min.time(), tzinfo=dt_timezone.utc)
            backtest = create_backtest_run(
                data["strategy"], data["symbol"], data["timeframe"],
                start, end, data["initial_capital"],
                engine_overrides=form.engine_overrides(),
            )
            run_backtest_task.delay(backtest.id)
            return redirect("backtest-detail", pk=backtest.id)
    else:
        form = BacktestRunForm()
    return render(request, "backtest/create.html", {"form": form})


def backtest_detail_view(request, pk):
    backtest = get_object_or_404(BacktestRun.objects.select_related("strategy", "symbol"), pk=pk)
    context = {"backtest": backtest, "exit_reasons": EXIT_REASON_CHOICES}
    if backtest.status == BacktestRun.Status.COMPLETED:
        chart_data = get_chart_data(backtest)
        context["chart_data_json"] = json.dumps(chart_data)
        context["top_winners"] = backtest.trades.order_by("-net_pnl")[:10]
        context["top_losers"] = backtest.trades.order_by("net_pnl")[:10]
    return render(request, "backtest/detail.html", context)


def backtest_status_partial_view(request, pk):
    backtest = get_object_or_404(BacktestRun, pk=pk)
    return render(request, "backtest/_status.html", {"backtest": backtest, "poll": True})


def backtest_trades_partial_view(request, pk):
    backtest = get_object_or_404(BacktestRun, pk=pk)
    trades = backtest.trades.all()

    side = request.GET.get("side", "")
    if side in ("LONG", "SHORT"):
        trades = trades.filter(side=side)

    outcome = request.GET.get("outcome", "")
    if outcome == "WIN":
        trades = trades.filter(net_pnl__gt=0)
    elif outcome == "LOSS":
        trades = trades.filter(net_pnl__lt=0)

    exit_reason = request.GET.get("exit_reason", "")
    if exit_reason in EXIT_REASON_CHOICES:
        trades = trades.filter(exit_reason=exit_reason)

    return render(request, "backtest/_trades_table.html", {
        "trades": trades, "backtest": backtest, "exit_reasons": EXIT_REASON_CHOICES,
        "selected_side": side, "selected_outcome": outcome, "selected_exit_reason": exit_reason,
    })


def backtest_compare_view(request):
    runs = (
        BacktestRun.objects.select_related("strategy")
        .filter(status=BacktestRun.Status.COMPLETED)
        .order_by("-created_at")
    )
    return render(request, "backtest/compare.html", {"runs": runs})
