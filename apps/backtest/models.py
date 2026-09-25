from django.db import models

from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig


class BacktestRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    strategy = models.ForeignKey(StrategyConfig, on_delete=models.CASCADE, related_name="backtest_runs")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="backtest_runs")
    timeframe = models.CharField(max_length=10)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    configuration = models.JSONField()  # BacktestEngineConfig used for this run
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)

    initial_capital = models.FloatField()
    final_capital = models.FloatField(null=True)
    # Performance metrics dict (see core/quant/metrics.py) plus a "benchmark" key
    # holding the buy&hold comparison over the same range. One JSON blob instead
    # of a separate BacktestMetric table/columns-per-metric -- adding a metric is
    # then a code change, not a migration.
    metrics = models.JSONField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    def __str__(self):
        return f"{self.strategy_id} {self.symbol_id} {self.start_date}..{self.end_date}"


class BacktestTrade(models.Model):
    backtest = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="trades")
    side = models.CharField(max_length=5)

    signal_timestamp = models.DateTimeField()
    entry_timestamp = models.DateTimeField()
    entry_price = models.FloatField()
    exit_timestamp = models.DateTimeField(null=True)
    exit_price = models.FloatField(null=True)
    stop_loss = models.FloatField()
    take_profit = models.FloatField()
    size = models.FloatField()

    fees = models.FloatField()
    slippage = models.FloatField()
    gross_pnl = models.FloatField()
    net_pnl = models.FloatField()
    return_pct = models.FloatField()
    exit_reason = models.CharField(max_length=20)
    equity_after = models.FloatField()

    class Meta:
        ordering = ["entry_timestamp"]

    def __str__(self):
        return f"{self.backtest_id} {self.side} {self.entry_timestamp}"
