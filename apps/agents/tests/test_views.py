from datetime import datetime, timezone as dt_timezone

import pytest

from apps.agents.models import AgentPipelineRun, AgentStepDecision
from apps.market.models import FeatureSnapshot, MarketSymbol
from apps.trading.models import LiveSignal

TS = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.fixture
def pipeline_run(symbol):
    snapshot = FeatureSnapshot.objects.create(symbol=symbol, timeframe="1h", timestamp=TS, rsi_14=65)
    signal = LiveSignal.objects.create(
        timestamp=TS, symbol=symbol, timeframe="1h", baseline_side="LONG", decision="LONG",
        model_probability=0.82, feature_snapshot=snapshot,
    )
    run = AgentPipelineRun.objects.create(
        signal=signal, final_recommendation="LONG",
        total_input_tokens=300, total_output_tokens=120, total_estimated_cost=0.0045, total_latency_ms=900,
    )
    for name, output in [
        ("technical_analyst", {"trend": "bullish", "strength": 0.8, "notes": "strong momentum"}),
        ("derivatives_analyst", {"positioning": "neutral", "risk_flag": False, "notes": "calm funding"}),
        ("sentiment_analyst", {"sentiment": "no_data", "notes": "no external source"}),
        ("bull_researcher", {"thesis": "trend continuation", "confidence": 0.8}),
        ("bear_researcher", {"thesis": "overbought risk", "confidence": 0.3}),
        ("trader", {"decision": "LONG", "confidence": 0.8, "reasoning": "bull case stronger"}),
        ("risk_reviewer", {"approved": True, "reason": "consistent with quant signal"}),
    ]:
        AgentStepDecision.objects.create(
            pipeline_run=run, agent_name=name, model="claude-opus-5", prompt_hash="x" * 64,
            output=output, input_tokens=40, output_tokens=15, estimated_cost=0.0006, latency_ms=120,
            cached=(name == "sentiment_analyst"),
        )
    return run


@pytest.mark.django_db
def test_list_view_shows_the_run(client, pipeline_run):
    response = client.get("/ai-agents/")

    assert response.status_code == 200
    assert b"BTCUSDT" in response.content
    assert b"LONG" in response.content


@pytest.mark.django_db
def test_detail_view_shows_every_step_in_order(client, pipeline_run):
    response = client.get(f"/ai-agents/{pipeline_run.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    trace_start = content.index("Pipeline trace")  # skip the "BTC Trader" sidebar logo above it
    positions = [content.index(label, trace_start) for label in (
        "Technical Analyst", "Derivatives Analyst", "Sentiment Analyst",
        "Bull Researcher", "Bear Researcher", "Trader", "Risk Reviewer",
    )]
    assert positions == sorted(positions)  # rendered in pipeline order
    assert "strong momentum" in content
    assert "consistent with quant signal" in content
