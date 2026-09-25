from django.db import models


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
