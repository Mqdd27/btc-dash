from django.db import models

from apps.trading.models import LiveSignal


class AgentDecision(models.Model):
    """One row per LiveSignal that reached the AI review gate -- whether it
    triggered a real API call or was served from cache (see `cached`).
    A LiveSignal only ever gets reviewed once, so this is one-to-one."""

    class Decision(models.TextChoices):
        TAKE = "TAKE", "Take"
        SKIP = "SKIP", "Skip"

    signal = models.OneToOneField(LiveSignal, on_delete=models.CASCADE, related_name="agent_decision")
    provider = models.CharField(max_length=30, default="anthropic")
    model = models.CharField(max_length=50)
    prompt_hash = models.CharField(max_length=64)  # sha256 hex, cache key together with `model`

    decision = models.CharField(max_length=4, choices=Decision.choices)
    confidence = models.FloatField()
    reason = models.CharField(max_length=200)

    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    estimated_cost = models.FloatField(null=True)  # null when the model's pricing isn't known
    latency_ms = models.FloatField()
    cached = models.BooleanField(default=False)  # True: reused a prior identical (prompt_hash, model) result

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["prompt_hash", "model"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.signal_id} {self.decision} ({self.confidence:.2f})"
