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


class AgentPipelineRun(models.Model):
    """One row per LiveSignal run through the full_agent TradingAgents pipeline.
    One-to-one, same as AgentDecision -- a signal is only ever put through the
    pipeline once. Rolls up totals across every AgentStepDecision it owns."""

    signal = models.OneToOneField(LiveSignal, on_delete=models.CASCADE, related_name="agent_pipeline_run")
    final_recommendation = models.CharField(max_length=5, choices=LiveSignal.Side.choices)
    total_input_tokens = models.PositiveIntegerField(default=0)
    total_output_tokens = models.PositiveIntegerField(default=0)
    total_estimated_cost = models.FloatField(null=True)
    total_latency_ms = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.signal_id} -> {self.final_recommendation}"


class AgentStepDecision(models.Model):
    """One row per agent in the TradingAgents pipeline (technical/derivatives/
    sentiment/bull/bear/trader/risk_reviewer) for a given AgentPipelineRun.
    `output` is a JSONField, not typed columns -- each agent's structured
    output has a different shape (Pydantic schema), and 7 near-empty tables
    for 7 small schemas would be the over-engineered choice, not this one."""

    AGENT_CHOICES = [
        ("technical_analyst", "Technical Analyst"),
        ("derivatives_analyst", "Derivatives Analyst"),
        ("sentiment_analyst", "Sentiment Analyst"),
        ("bull_researcher", "Bull Researcher"),
        ("bear_researcher", "Bear Researcher"),
        ("trader", "Trader"),
        ("risk_reviewer", "Risk Reviewer"),
    ]

    pipeline_run = models.ForeignKey(AgentPipelineRun, on_delete=models.CASCADE, related_name="steps")
    agent_name = models.CharField(max_length=30, choices=AGENT_CHOICES)
    model = models.CharField(max_length=50)
    prompt_hash = models.CharField(max_length=64)

    output = models.JSONField()
    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    estimated_cost = models.FloatField(null=True)
    latency_ms = models.FloatField()
    cached = models.BooleanField(default=False)  # also True for the sentiment stub (see trading_agents.py) -- no real call made

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["agent_name", "prompt_hash", "model"])]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.pipeline_run_id} {self.agent_name}"
