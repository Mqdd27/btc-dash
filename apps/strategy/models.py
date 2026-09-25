from django.db import models

from apps.market.models import FeatureSnapshot, MarketSymbol

# The FeatureSnapshot columns strategies are allowed to read EMA values from --
# only spans Phase 3 actually precomputes.
EMA_SPAN_CHOICES = [(10, "10"), (20, "20"), (50, "50"), (100, "100"), (200, "200")]


class StrategyConfig(models.Model):
    name = models.CharField(max_length=50, unique=True)  # registry key, e.g. "ema_rsi"
    enabled = models.BooleanField(default=True)
    timeframe = models.CharField(max_length=10, default="1h")

    ema_fast = models.PositiveIntegerField(choices=EMA_SPAN_CHOICES, default=20)
    ema_slow = models.PositiveIntegerField(choices=EMA_SPAN_CHOICES, default=50)
    rsi_long_threshold = models.FloatField(default=55)
    rsi_short_threshold = models.FloatField(default=45)
    atr_sl_multiplier = models.FloatField(default=1.5)
    atr_tp_multiplier = models.FloatField(default=3.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SignalCandidate(models.Model):
    class Side(models.TextChoices):
        LONG = "LONG", "Long"
        SHORT = "SHORT", "Short"

    strategy = models.ForeignKey(StrategyConfig, on_delete=models.CASCADE, related_name="signal_candidates")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="signal_candidates")
    timeframe = models.CharField(max_length=10)
    candle_timestamp = models.DateTimeField()
    side = models.CharField(max_length=5, choices=Side.choices)

    entry_reference_price = models.FloatField()
    stop_loss_reference = models.FloatField()
    take_profit_reference = models.FloatField()

    feature_snapshot = models.ForeignKey(FeatureSnapshot, on_delete=models.CASCADE, related_name="signal_candidates")
    strategy_version = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "symbol", "timeframe", "candle_timestamp"],
                name="unique_signal_candidate",
            )
        ]
        ordering = ["candle_timestamp"]

    def __str__(self):
        return f"{self.strategy_id} {self.symbol_id} {self.candle_timestamp} {self.side}"
