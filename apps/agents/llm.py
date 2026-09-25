"""Shared low-level Claude call: structured output only, no chat/tool use.
Used by both the single reviewer (Phase 11) and the TradingAgents pipeline
(Phase 12) -- the mechanics of "call Claude, get back a validated Pydantic
object" are identical, only the prompts/schemas differ per caller.
"""

import time

from django.conf import settings

# $ per 1M tokens, published Anthropic pricing. Unlisted model -> cost stays None.
MODEL_PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def call_claude_structured(system_prompt: str, user_prompt: str, output_schema):
    import anthropic

    client = anthropic.Anthropic()
    start = time.monotonic()
    response = client.messages.parse(
        model=settings.AI_MODEL,
        max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=output_schema,
    )
    latency_ms = (time.monotonic() - start) * 1000
    return response.parsed_output, response.usage.input_tokens, response.usage.output_tokens, latency_ms


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    input_rate, output_rate = pricing
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
