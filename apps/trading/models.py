from django.db import models

from apps.market.models import FeatureSnapshot, MarketSymbol
from apps.ml.models import ModelVersion


class EngineConfig(models.Model):
    class Mode(models.TextChoices):
        QUANT = "quant", "Quant"
        QUANT_AI = "quant_ai", "Quant + AI"
        FULL_AGENT = "full_agent", "Full Agent"

    class Timeframe(models.TextChoices):
        M15 = "15m", "15m"
        H1 = "1h", "1H"
        H4 = "4h", "4H"

    class ExecutionMode(models.TextChoices):
        DISABLED = "disabled", "Disabled"
        PAPER = "paper", "Paper"
        LIVE = "live", "Live"

    # Safety default: engine off, no order execution until explicitly turned on.
    enabled = models.BooleanField(default=False)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.QUANT)
    timeframe = models.CharField(max_length=10, choices=Timeframe.choices, default=Timeframe.H1)
    execution_mode = models.CharField(
        max_length=20, choices=ExecutionMode.choices, default=ExecutionMode.DISABLED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EngineConfig(enabled={self.enabled}, mode={self.mode}, execution={self.execution_mode})"


class LiveSignal(models.Model):
    """One row per candle-close evaluation by the live engine -- including WAIT
    decisions, unlike apps.strategy.SignalCandidate. This is the audit trail
    behind the dashboard's "last evaluation"/"last signal"/inference counter."""

    class Side(models.TextChoices):
        LONG = "LONG", "Long"
        SHORT = "SHORT", "Short"
        WAIT = "WAIT", "Wait"

    timestamp = models.DateTimeField()  # the finalized candle's own timestamp
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="live_signals")
    timeframe = models.CharField(max_length=10)

    baseline_side = models.CharField(max_length=5, choices=Side.choices)
    model_probability = models.FloatField(null=True)  # null when no active model or baseline was WAIT
    decision = models.CharField(max_length=5, choices=Side.choices)

    model_version = models.ForeignKey(
        ModelVersion, on_delete=models.SET_NULL, null=True, related_name="live_signals"
    )
    feature_snapshot = models.ForeignKey(FeatureSnapshot, on_delete=models.CASCADE, related_name="live_signals")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["symbol", "timeframe", "timestamp"], name="unique_live_signal")
        ]
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.symbol_id} {self.timeframe} {self.timestamp} {self.decision}"
