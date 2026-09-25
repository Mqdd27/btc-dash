import pytest

from apps.backtest.models import BacktestRun
from apps.backtest.services import create_backtest_run
from apps.backtest.tasks import run_backtest_task

from .test_services import seed_data, strategy_config, symbol  # noqa: F401


@pytest.mark.django_db
def test_task_executes_a_queued_run(symbol, strategy_config):  # noqa: F811
    start, end = seed_data(symbol)
    backtest = create_backtest_run(strategy_config, symbol, "1h", start, end, initial_capital=10000)
    assert backtest.status == BacktestRun.Status.QUEUED

    run_backtest_task(backtest.id)  # call directly, no broker needed for this

    backtest.refresh_from_db()
    assert backtest.status == BacktestRun.Status.COMPLETED
    assert backtest.metrics is not None
