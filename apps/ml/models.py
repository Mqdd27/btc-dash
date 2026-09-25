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
