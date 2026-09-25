from celery import shared_task

from .models import BacktestRun
from .services import execute_backtest


@shared_task
def run_backtest_task(backtest_run_id: int) -> None:
    backtest = BacktestRun.objects.get(id=backtest_run_id)
    execute_backtest(backtest)
