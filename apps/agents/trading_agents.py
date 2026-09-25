"""TradingAgents, adapted for BTC: a 7-agent pipeline (technical/derivatives/
sentiment analysts -> bull/bear researchers -> trader -> risk reviewer) that
only ever runs as the tail of the same evaluate_now() pipeline everything
else uses, for candidates that already cleared the XGBoost probability gate
-- exactly like the single reviewer (Phase 11), just a longer chain.

TradingAgents is an optional layer: full_agent mode is the only thing that
calls run_trading_agents(); "quant" and "quant_ai" mode never import this
module at all (see apps/trading/tasks.py). Disabling full_agent (switching
back to "quant" or AI_ENABLED=False) leaves quant-mode operation untouched.

No stock-market company fundamentals -- there are none for BTC. Liquidation
data has no source anywhere in this codebase yet, so it's passed as `None`
("when available", currently never). Sentiment/news has no external data
source integrated either; rather than spend a real, knowably-uninformative
call asking the model to comment on data it doesn't have, the sentiment
"agent" is a local structural stub -- see run_sentiment_analyst().
"""

import hashlib
import json

from django.conf import settings
from pydantic import BaseModel

from apps.strategy.services import STRATEGIES
from apps.trading.models import LiveSignal

from .llm import call_claude_structured, estimate_cost
from .models import AgentPipelineRun, AgentStepDecision
from .reviewer import build_context, daily_call_count


class TechnicalView(BaseModel):
    trend: str  # "bullish" | "bearish" | "neutral"
    strength: float
    notes: str


class DerivativesView(BaseModel):
    positioning: str  # "long_heavy" | "short_heavy" | "neutral"
    risk_flag: bool
    notes: str


class SentimentView(BaseModel):
    sentiment: str  # "positive" | "negative" | "neutral" | "no_data"
    notes: str


class ResearchThesis(BaseModel):
    thesis: str
    confidence: float


class TraderDecision(BaseModel):
    decision: str  # "LONG" | "SHORT" | "WAIT"
    confidence: float
    reasoning: str


class RiskReview(BaseModel):
    approved: bool
    reason: str


SYSTEM_PROMPTS = {
    "technical_analyst": (
        "You are the Technical Analyst. Use only the precomputed technical values "
        "given to you (RSI, EMA trend, ATR, volatility) -- do not calculate your own "
        "indicators. Be terse."
    ),
    "derivatives_analyst": (
        "You are the Derivatives Analyst. Assess funding rate, funding change, open "
        "interest change, and liquidation data (if present) for crowding/squeeze risk. "
        "Be terse."
    ),
    "bull_researcher": "You are the Bull Researcher. Build the strongest case FOR this trade. Be terse.",
    "bear_researcher": "You are the Bear Researcher. Build the strongest case AGAINST this trade. Be terse.",
    "trader": (
        "You are the Trader. Weigh the quant signal, technical/derivatives reads, and "
        "the bull/bear cases. Decide LONG, SHORT, or WAIT. Be terse."
    ),
    "risk_reviewer": (
        "You are the Risk Reviewer, the final gate. Approve only if the Trader's "
        "reasoning is sound and consistent with the quant signal; otherwise reject. Be terse."
    ),
}


def build_quant_context(live_signal: LiveSignal) -> dict:
    """The quant context the spec requires in every stage: baseline signal,
    XGBoost probability, historical similar-setup stats (via reviewer.build_context),
    plus strategy version and model version."""
    context = build_context(live_signal)
    context["liquidation_data"] = None  # not available in this codebase yet
    if live_signal.model_version is not None:
        strategy_cls = STRATEGIES.get(live_signal.model_version.strategy.name)
        context["strategy_version"] = strategy_cls.version if strategy_cls else None
        context["model_version"] = live_signal.model_version.name
    else:
        context["strategy_version"] = None
        context["model_version"] = None
    return context


def run_agent_step(pipeline_run: AgentPipelineRun, agent_name: str, context: dict, output_schema) -> AgentStepDecision:
    prompt = json.dumps(context, default=str)
    prompt_hash = hashlib.sha256(f"{agent_name}:{prompt}".encode()).hexdigest()

    cached = (
        AgentStepDecision.objects.filter(agent_name=agent_name, prompt_hash=prompt_hash, model=settings.AI_MODEL)
        .order_by("created_at").first()
    )
    if cached is not None:
        return AgentStepDecision.objects.create(
            pipeline_run=pipeline_run, agent_name=agent_name, model=settings.AI_MODEL, prompt_hash=prompt_hash,
            output=cached.output, input_tokens=0, output_tokens=0, estimated_cost=0.0, latency_ms=0.0, cached=True,
        )

    parsed, input_tokens, output_tokens, latency_ms = call_claude_structured(
        SYSTEM_PROMPTS[agent_name], prompt, output_schema
    )
    return AgentStepDecision.objects.create(
        pipeline_run=pipeline_run, agent_name=agent_name, model=settings.AI_MODEL, prompt_hash=prompt_hash,
        output=parsed.model_dump(), input_tokens=input_tokens, output_tokens=output_tokens,
        estimated_cost=estimate_cost(settings.AI_MODEL, input_tokens, output_tokens),
        latency_ms=latency_ms, cached=False,
    )


def run_sentiment_analyst(pipeline_run: AgentPipelineRun) -> AgentStepDecision:
    """No external news/sentiment source is integrated anywhere in this codebase.
    Asking an LLM to comment on data it doesn't have is a knowably wasted call --
    so this is a local stub, not a real API call. cached=True keeps it out of the
    daily budget, same convention as an actual cache hit.
    """
    output = SentimentView(sentiment="no_data", notes="no external sentiment/news source integrated").model_dump()
    return AgentStepDecision.objects.create(
        pipeline_run=pipeline_run, agent_name="sentiment_analyst", model=settings.AI_MODEL,
        prompt_hash="stub", output=output, input_tokens=0, output_tokens=0,
        estimated_cost=0.0, latency_ms=0.0, cached=True,
    )


def run_trading_agents(live_signal: LiveSignal) -> AgentPipelineRun | None:
    """May downgrade live_signal.decision to WAIT (or set it to the Trader's
    LONG/SHORT call) in place. Returns None -- leaving live_signal untouched --
    whenever the pipeline is skipped entirely: AI disabled, below the
    AI-specific probability bar, or the daily call budget is already spent.
    Never called for every candle -- see apps/trading/tasks.py, which only
    calls this for a signal whose baseline decision is already LONG/SHORT.
    """
    if not settings.AI_ENABLED:
        return None
    if live_signal.model_probability is None or live_signal.model_probability < settings.AI_MIN_QUANT_PROBABILITY:
        return None
    if daily_call_count() >= settings.AI_DAILY_CALL_LIMIT:
        return None

    quant_context = build_quant_context(live_signal)
    pipeline_run = AgentPipelineRun.objects.create(signal=live_signal, final_recommendation=LiveSignal.Side.WAIT)

    technical = run_agent_step(pipeline_run, "technical_analyst", quant_context, TechnicalView)
    derivatives = run_agent_step(pipeline_run, "derivatives_analyst", quant_context, DerivativesView)
    sentiment = run_sentiment_analyst(pipeline_run)

    research_context = {
        **quant_context, "technical": technical.output, "derivatives": derivatives.output, "sentiment": sentiment.output,
    }
    bull = run_agent_step(pipeline_run, "bull_researcher", research_context, ResearchThesis)
    bear = run_agent_step(pipeline_run, "bear_researcher", research_context, ResearchThesis)

    trader_context = {**research_context, "bull_case": bull.output, "bear_case": bear.output}
    trader = run_agent_step(pipeline_run, "trader", trader_context, TraderDecision)

    risk_context = {**quant_context, "trader_decision": trader.output}
    risk = run_agent_step(pipeline_run, "risk_reviewer", risk_context, RiskReview)

    final = trader.output["decision"] if risk.output["approved"] else LiveSignal.Side.WAIT.value

    steps = pipeline_run.steps.all()
    pipeline_run.final_recommendation = final
    pipeline_run.total_input_tokens = sum(s.input_tokens for s in steps)
    pipeline_run.total_output_tokens = sum(s.output_tokens for s in steps)
    costs = [s.estimated_cost for s in steps if s.estimated_cost is not None]
    pipeline_run.total_estimated_cost = sum(costs) if costs else None
    pipeline_run.total_latency_ms = sum(s.latency_ms for s in steps)
    pipeline_run.save()

    live_signal.decision = final
    live_signal.save(update_fields=["decision"])

    return pipeline_run
