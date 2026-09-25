from django.db import models

from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig


class ModelVersion(models.Model):
    name = models.CharField(max_length=100)
    algorithm = models.CharField(max_length=30, default="xgboost")

    # Which strategy's candidates this model was trained to filter. Not in the
    # spec's field list verbatim, but required for the model to be usable at all.
    strategy = models.ForeignKey(StrategyConfig, on_delete=models.CASCADE, related_name="model_versions")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="model_versions")
    timeframe = models.CharField(max_length=10)

    training_start = models.DateTimeField()
    training_end = models.DateTimeField()
    features = models.JSONField()  # ordered list of feature column names used
    hyperparameters = models.JSONField()
    # {"validation": {...}, "test": {...}, "trading_comparison": {...}} -- filled
    # in progressively by training (validation) then evaluation (test + comparison).
    validation_metrics = models.JSONField(null=True)

    model_file = models.CharField(max_length=255)  # path under MEDIA_ROOT
    active = models.BooleanField(default=False)  # safety default, same pattern as EngineConfig
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.algorithm}, {self.strategy_id}/{self.symbol_id}/{self.timeframe})"


class WalkForwardRun(models.Model):
    class Mode(models.TextChoices):
        ROLLING = "rolling", "Rolling"
        EXPANDING = "expanding", "Expanding"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    strategy = models.ForeignKey(StrategyConfig, on_delete=models.CASCADE, related_name="walk_forward_runs")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="walk_forward_runs")
    timeframe = models.CharField(max_length=10)
    mode = models.CharField(max_length=10, choices=Mode.choices)

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    training_months = models.PositiveIntegerField(default=24)
    test_months = models.PositiveIntegerField(default=3)
    retrain_months = models.PositiveIntegerField(default=3)
    probability_threshold = models.FloatField(default=0.65)
    hyperparameters = models.JSONField()

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    # compute_metrics() output over the concatenation of every window's TEST-window
    # trades only, in chronological order -- never training-period performance.
    aggregate_metrics = models.JSONField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    def __str__(self):
        return f"{self.strategy_id} {self.symbol_id} {self.mode} {self.start_date}..{self.end_date}"


class WalkForwardWindow(models.Model):
    run = models.ForeignKey(WalkForwardRun, on_delete=models.CASCADE, related_name="windows")
    index = models.PositiveIntegerField()

    train_start = models.DateTimeField()
    train_end = models.DateTimeField()
    test_start = models.DateTimeField()
    test_end = models.DateTimeField()

    model_file = models.CharField(max_length=255)  # this window's own freshly-trained model, path under MEDIA_ROOT
    # compute_metrics() output for this window's test-period trades only.
    metrics = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["run", "index"], name="unique_walk_forward_window")
        ]

    def __str__(self):
        return f"{self.run_id} window {self.index}"
