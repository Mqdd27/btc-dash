"""Thin ccxt wrapper: exchange clients + retry with bounded exponential backoff."""

import logging
import time

import ccxt

logger = logging.getLogger(__name__)

# Transient errors worth retrying. Anything else (bad symbol, auth, etc.) fails fast.
RETRYABLE_ERRORS = (
    ccxt.NetworkError,
    ccxt.ExchangeNotAvailable,
    ccxt.RequestTimeout,
    ccxt.DDoSProtection,
    ccxt.RateLimitExceeded,
)


def get_spot_exchange():
    return ccxt.binance({"enableRateLimit": True})


def get_futures_exchange():
    """USDT-margined perpetuals: source of funding-rate / open-interest history."""
    return ccxt.binanceusdm({"enableRateLimit": True})


def call_with_retry(fn, *args, max_retries=5, base_delay=1.0, **kwargs):
    """Call fn(*args, **kwargs), retrying transient ccxt errors with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except RETRYABLE_ERRORS as exc:
            if attempt == max_retries:
                logger.error("giving up after %d retries: %s", max_retries, exc)
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "request failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            time.sleep(delay)
