from datetime import datetime, timezone as dt_timezone

import pytest

from apps.agents.models import AgentDecision
from apps.agents.services import get_ai_reviewer_stats
from apps.market.models import FeatureSnapshot, MarketSymbol
from apps.trading.models import LiveSignal

TS = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.mark.django_db
def test_stats_separate_real_calls_from_cache_hits(symbol, settings):
    settings.AI_ENABLED = True
    settings.AI_DAILY_CALL_LIMIT = 50

    snapshot = FeatureSnapshot.objects.create(symbol=symbol, timeframe="1h", timestamp=TS)
    signal = LiveSignal.objects.create(
        timestamp=TS, symbol=symbol, timeframe="1h", baseline_side="LONG", decision="LONG",
        feature_snapshot=snapshot, model_probability=0.9,
    )
    AgentDecision.objects.create(
        signal=signal, model="claude-opus-5", prompt_hash="a" * 64, decision="TAKE",
        confidence=0.9, reason="x", input_tokens=100, output_tokens=20,
        estimated_cost=0.001, latency_ms=250, cached=False,
    )

    snapshot2 = FeatureSnapshot.objects.create(symbol=symbol, timeframe="4h", timestamp=TS)
    signal2 = LiveSignal.objects.create(
        timestamp=TS, symbol=symbol, timeframe="4h", baseline_side="LONG", decision="LONG",
        feature_snapshot=snapshot2, model_probability=0.9,
    )
    AgentDecision.objects.create(
        signal=signal2, model="claude-opus-5", prompt_hash="a" * 64, decision="TAKE",
        confidence=0.9, reason="x", input_tokens=0, output_tokens=0,
        estimated_cost=0.0, latency_ms=0, cached=True,
    )

    stats = get_ai_reviewer_stats()

    assert stats["calls_today"] == 1
    assert stats["cache_hits_today"] == 1
    assert stats["input_tokens_today"] == 100
    assert stats["output_tokens_today"] == 20
    assert stats["estimated_cost_today"] == 0.001
    assert stats["ai_enabled"] is True
