from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import ccxt
import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.market import services
from apps.market.exchange import call_with_retry
from apps.market.models import Candle, FundingRate, MarketSymbol, OpenInterest

H = 3600 * 1000  # one hour in ms


def dt(hour, day=1):
    return datetime(2024, 1, day, hour, tzinfo=dt_timezone.utc)


def row(hour, day=1, close=100.0):
    ms = int(dt(hour, day).timestamp() * 1000)
    return [ms, 100.0, 101.0, 99.0, close, 10.0]


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


class FakeExchange:
    """Minimal ccxt stand-in: serves fetch_ohlcv from a scripted page list."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self._real = ccxt.binance()

    def parse_timeframe(self, tf):
        return self._real.parse_timeframe(tf)

    def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        self.calls.append(since)
        return self.pages.pop(0) if self.pages else []


@pytest.mark.django_db
def test_unique_candle_constraint(symbol):
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=dt(10),
        open=1, high=1, low=1, close=1, volume=1,
    )
    with pytest.raises(IntegrityError):
        Candle.objects.create(
            symbol=symbol, timeframe="1h", timestamp=dt(10),
            open=2, high=2, low=2, close=2, volume=2,
        )


@pytest.mark.django_db
def test_historical_pagination_advances_and_stops(symbol):
    pages = [
        [row(10), row(11)],
        [row(12), row(13)],
        [],
    ]
    fake = FakeExchange(pages)
    count = services.fetch_historical(symbol, "1h", dt(10), dt(13), exchange=fake)

    assert count == 4
    assert Candle.objects.filter(symbol=symbol, timeframe="1h").count() == 4
    # second page's `since` should follow directly from the first page's last candle
    assert fake.calls[1] == int(dt(11).timestamp() * 1000) + 1


@pytest.mark.django_db
def test_duplicate_handling_is_idempotent(symbol):
    pages = [[row(10), row(11)], []]
    services.fetch_historical(symbol, "1h", dt(10), dt(11), exchange=FakeExchange(pages))
    assert Candle.objects.count() == 2

    # re-running the same range must not create duplicates
    services.fetch_historical(symbol, "1h", dt(10), dt(11), exchange=FakeExchange([[row(10), row(11)], []]))
    assert Candle.objects.count() == 2


@pytest.mark.django_db
def test_closed_candle_is_not_overwritten_by_incomplete_data(symbol):
    # timestamp is inside the current, still-forming hour, so a fresh fetch
    # recomputes is_closed=False for it -- but the stored row is (correctly
    # or not) already marked closed, and must not be downgraded.
    current_open = timezone.now().replace(minute=0, second=0, microsecond=0)
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=current_open,
        open=1, high=1, low=1, close=1, volume=1, closed=True,
    )
    ms = int(current_open.timestamp() * 1000)
    written = services.upsert_candles(symbol, "1h", [[ms, 9, 9, 9, 9, 9]])

    candle = Candle.objects.get(symbol=symbol, timeframe="1h", timestamp=current_open)
    assert written == 0
    assert candle.close == 1  # untouched, not overwritten with the incomplete "9" values
    assert candle.closed is True


@pytest.mark.django_db
def test_incremental_update_only_fetches_from_last_known_candle(symbol):
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=dt(10),
        open=1, high=1, low=1, close=1, volume=1,
    )
    fake = FakeExchange([[row(11)], []])
    services.update_recent(symbol, "1h", exchange=fake)

    assert fake.calls[0] == int(dt(10).timestamp() * 1000)
    assert Candle.objects.filter(symbol=symbol, timeframe="1h").count() == 2


@pytest.mark.django_db
def test_missing_candle_detection_reports_gap_without_fabricating(symbol):
    for h in (10, 11, 13):
        Candle.objects.create(
            symbol=symbol, timeframe="1h", timestamp=dt(h),
            open=1, high=1, low=1, close=1, volume=1,
        )
    missing = services.find_missing_candles(symbol, "1h", dt(10), dt(13))

    assert missing == [dt(12)]
    assert Candle.objects.filter(timestamp=dt(12)).exists() is False


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ccxt.NetworkError("timeout")
        return "ok"

    with patch("apps.market.exchange.time.sleep"):
        assert call_with_retry(flaky, max_retries=5, base_delay=0.01) == "ok"
    assert calls["n"] == 3


def test_retry_gives_up_after_max_retries():
    def always_fails():
        raise ccxt.NetworkError("down")

    with patch("apps.market.exchange.time.sleep"):
        with pytest.raises(ccxt.NetworkError):
            call_with_retry(always_fails, max_retries=2, base_delay=0.01)
