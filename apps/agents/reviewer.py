"""Single AI reviewer: one LLM call, only for quant candidates that already
cleared the XGBoost probability threshold. Never called on every candle --
see review_candidate()'s early-return guards, all of which mean 0 AI calls.
"""

import hashlib
import json
import time

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel

from apps.backtest.models import BacktestTrade
from apps.trading.models import LiveSignal

from .models import AgentDecision

# $ per 1M tokens, from Anthropic's published pricing. Extend as needed --
# an unlisted model just means estimated_cost stays None ("if available").
MODEL_PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class ReviewOutput(BaseModel):
    decision: str  # "TAKE" | "SKIP"
    confidence: float
    reason: str


def build_context(live_signal: LiveSignal) -> dict:
    """Concise structured context -- exactly the fields the spec lists, no more."""
    snapshot = live_signal.feature_snapshot
    return {
        "symbol": live_signal.symbol.symbol,
        "timeframe": live_signal.timeframe,
        "candidate_side": live_signal.baseline_side,
        "xgboost_probability": round(live_signal.model_probability, 4),
        "rsi": snapshot.rsi_14,
        "ema_trend": _ema_trend(snapshot),
        "atr_percent": snapshot.atr_percent,
        "volatility": snapshot.rolling_volatility,
        "volume_change": snapshot.volume_change,
        "funding_rate": snapshot.funding_rate,
        "open_interest_change": snapshot.open_interest_change,
        "historical_similar_setup": historical_stats(live_signal),
    }


def _ema_trend(snapshot) -> str | None:
    if snapshot.ema20_vs_ema50 is None:
        return None
    return "bullish" if snapshot.ema20_vs_ema50 > 0 else "bearish"


def historical_stats(live_signal: LiveSignal) -> dict | None:
    """Cheapest available "similar setup" proxy: this strategy's own historical
    backtest trades on the same symbol/timeframe/side. Skipped (None) if the
    signal has no model_version to trace back to a strategy."""
    if live_signal.model_version is None:
        return None
    trades = BacktestTrade.objects.filter(
        backtest__strategy=live_signal.model_version.strategy,
        backtest__symbol=live_signal.symbol,
        backtest__timeframe=live_signal.timeframe,
        side=live_signal.baseline_side,
    )
    count = trades.count()
    if count == 0:
        return None
    wins = trades.filter(net_pnl__gt=0).count()
    return {"sample_size": count, "historical_win_rate_pct": round(wins / count * 100, 1)}


def render_prompt(context: dict) -> str:
    return (
        "Review this quant trading candidate. Respond with TAKE only if there is a "
        "clear reason to trust it beyond the model probability; otherwise SKIP.\n\n"
        f"{json.dumps(context, default=str)}"
    )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    input_rate, output_rate = pricing
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def daily_call_count() -> int:
    """Real API calls only -- cache hits are free and don't count against the limit."""
    return AgentDecision.objects.filter(cached=False, created_at__date=timezone.now().date()).count()


def call_claude(prompt: str) -> tuple[ReviewOutput, int, int, float]:
    import anthropic

    client = anthropic.Anthropic()
    start = time.monotonic()
    response = client.messages.parse(
        model=settings.AI_MODEL,
        max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        system=(
            "You are a terse trading-signal reviewer. Reply with only the "
            "requested structured fields -- no preamble, no extra commentary."
        ),
        messages=[{"role": "user", "content": prompt}],
        output_format=ReviewOutput,
    )
    latency_ms = (time.monotonic() - start) * 1000
    return response.parsed_output, response.usage.input_tokens, response.usage.output_tokens, latency_ms


def review_candidate(live_signal: LiveSignal) -> AgentDecision | None:
    """May downgrade live_signal.decision to WAIT in place if the reviewer says
    SKIP. Returns None (and leaves live_signal untouched) whenever the AI is
    skipped entirely: disabled, below the AI-specific probability bar, or the
    daily call limit is already reached -- all of which fall back to
    quant-only behavior, per the safety configuration.
    """
    if not settings.AI_ENABLED:
        return None
    if live_signal.model_probability is None or live_signal.model_probability < settings.AI_MIN_QUANT_PROBABILITY:
        return None
    if daily_call_count() >= settings.AI_DAILY_CALL_LIMIT:
        return None

    context = build_context(live_signal)
    prompt = render_prompt(context)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

    cached = (
        AgentDecision.objects.filter(prompt_hash=prompt_hash, model=settings.AI_MODEL)
        .order_by("created_at").first()
    )
    if cached is not None:
        decision = AgentDecision.objects.create(
            signal=live_signal, provider="anthropic", model=settings.AI_MODEL, prompt_hash=prompt_hash,
            decision=cached.decision, confidence=cached.confidence, reason=cached.reason,
            input_tokens=0, output_tokens=0, estimated_cost=0.0, latency_ms=0.0, cached=True,
        )
    else:
        result, input_tokens, output_tokens, latency_ms = call_claude(prompt)
        decision = AgentDecision.objects.create(
            signal=live_signal, provider="anthropic", model=settings.AI_MODEL, prompt_hash=prompt_hash,
            decision=result.decision, confidence=result.confidence, reason=result.reason[:200],
            input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost=estimate_cost(settings.AI_MODEL, input_tokens, output_tokens),
            latency_ms=latency_ms, cached=False,
        )

    if decision.decision == AgentDecision.Decision.SKIP:
        live_signal.decision = LiveSignal.Side.WAIT
        live_signal.save(update_fields=["decision"])

    return decision
