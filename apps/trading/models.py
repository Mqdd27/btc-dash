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
    # The baseline strategy's own SL/TP reference, carried through so paper
    # trading (Phase 10) doesn't have to recompute the strategy's decision --
    # null when the decision was WAIT.
    stop_loss = models.FloatField(null=True)
    take_profit = models.FloatField(null=True)

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


class PaperAccount(models.Model):
    """Singleton (pk=1), same pattern as EngineConfig. Purely virtual -- never
    touches a real exchange. cash_balance only moves on a realized PaperTrade
    close (same "equity changes on trade close, not intrabar" convention the
    backtest engine uses); equity is cash_balance mark-to-marked with open
    positions' unrealized PnL, recomputed each time the paper engine runs."""

    initial_balance = models.FloatField(default=10000)
    cash_balance = models.FloatField(default=10000)
    equity = models.FloatField(default=10000)
    # Stops NEW positions from opening. Existing open positions keep being
    # monitored and can still hit SL/TP while paused -- pausing never leaves
    # risk unmanaged, and per the spec, never deletes positions or history.
    paused = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PaperAccount(cash={self.cash_balance:.2f}, equity={self.equity:.2f}, paused={self.paused})"


class PaperPosition(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"  # signaled, waiting for next candle's open to fill
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class Side(models.TextChoices):
        LONG = "LONG", "Long"
        SHORT = "SHORT", "Short"

    account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="positions")
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="paper_positions")
    timeframe = models.CharField(max_length=10)
    side = models.CharField(max_length=5, choices=Side.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # The LiveSignal that triggered this position -- "approved LONG/SHORT signal".
    signal = models.ForeignKey(LiveSignal, on_delete=models.SET_NULL, null=True, related_name="paper_positions")

    # Set once filled (status -> open), null while pending.
    entry_timestamp = models.DateTimeField(null=True)
    entry_price = models.FloatField(null=True)
    size = models.FloatField(null=True)
    entry_fee = models.FloatField(null=True)
    entry_slippage = models.FloatField(null=True)

    stop_loss = models.FloatField()
    take_profit = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)  # when the position was queued (signal time)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.symbol_id} {self.side} {self.status}"


class PaperTrade(models.Model):
    position = models.OneToOneField(PaperPosition, on_delete=models.CASCADE, related_name="trade")
    exit_timestamp = models.DateTimeField()
    exit_price = models.FloatField()
    fees = models.FloatField()
    pnl = models.FloatField()
    return_pct = models.FloatField()
    exit_reason = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-exit_timestamp"]

    def __str__(self):
        return f"{self.position_id} {self.exit_reason} pnl={self.pnl:.2f}"
