"""Market data business logic: fetch, upsert, gap detection. No views/commands here."""

import logging
from datetime import timedelta, timezone as dt_timezone

from django.utils import timezone

from .exchange import call_with_retry, get_futures_exchange, get_spot_exchange
from .models import Candle, FundingRate, MarketSymbol, OpenInterest

logger = logging.getLogger(__name__)

PAGE_LIMIT = 1000


def resolve_market_symbol(symbol_code: str, exchange=None) -> MarketSymbol:
    """Get or create the MarketSymbol row, looking up base/quote from the exchange."""
    try:
        return MarketSymbol.objects.get(symbol=symbol_code)
    except MarketSymbol.DoesNotExist:
        pass

    exchange = exchange or get_spot_exchange()
    call_with_retry(exchange.load_markets)
    market = exchange.markets_by_id.get(symbol_code)
    if not market:
        raise ValueError(f"Unknown symbol on {exchange.id}: {symbol_code}")
    market = market[0] if isinstance(market, list) else market

    return MarketSymbol.objects.create(
        symbol=symbol_code,
        base_asset=market["base"],
        quote_asset=market["quote"],
        exchange="binance",
    )


def spot_ccxt_symbol(market_symbol: MarketSymbol) -> str:
    return f"{market_symbol.base_asset}/{market_symbol.quote_asset}"


def swap_ccxt_symbol(market_symbol: MarketSymbol) -> str:
    return f"{market_symbol.base_asset}/{market_symbol.quote_asset}:{market_symbol.quote_asset}"


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _from_ms(ms):
    return timezone.datetime.fromtimestamp(ms / 1000, tz=dt_timezone.utc)


def upsert_candles(market_symbol: MarketSymbol, timeframe: str, rows: list[list]) -> int:
    """rows: ccxt OHLCV rows [ms, open, high, low, close, volume].

    Never overwrites a finalized (closed) candle with incomplete data.
    Returns the number of rows written (created or updated).
    """
    if not rows:
        return 0

    interval = timedelta(seconds=get_spot_exchange().parse_timeframe(timeframe))
    now = timezone.now()

    timestamps = [_from_ms(row[0]) for row in rows]
    existing = {
        c.timestamp: c
        for c in Candle.objects.filter(
            symbol=market_symbol, timeframe=timeframe, timestamp__in=timestamps
        )
    }

    to_create, to_update = [], []
    for row, ts in zip(rows, timestamps):
        _, o, h, l, c, v = row[:6]
        is_closed = (ts + interval) <= now

        current = existing.get(ts)
        if current is not None:
            if current.closed and not is_closed:
                continue  # ponytail: skip write, don't downgrade a finalized candle
            current.open, current.high, current.low, current.close, current.volume = o, h, l, c, v
            current.closed = is_closed
            to_update.append(current)
        else:
            to_create.append(
                Candle(
                    symbol=market_symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=v,
                    closed=is_closed,
                )
            )

    if to_create:
        Candle.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        Candle.objects.bulk_update(
            to_update, ["open", "high", "low", "close", "volume", "closed"]
        )
    return len(to_create) + len(to_update)


def fetch_historical(market_symbol: MarketSymbol, timeframe: str, start, end, exchange=None) -> int:
    """Paginate ccxt OHLCV from start to end (inclusive), upserting as we go.

    Idempotent: re-running the same range only updates non-finalized rows, so
    a resumed/repeated run never duplicates data (unique constraint + upsert).
    """
    exchange = exchange or get_spot_exchange()
    ccxt_symbol = spot_ccxt_symbol(market_symbol)
    since = _ms(start)
    end_ms = _ms(end)
    total = 0

    while since <= end_ms:
        rows = call_with_retry(
            exchange.fetch_ohlcv, ccxt_symbol, timeframe=timeframe, since=since, limit=PAGE_LIMIT
        )
        if not rows:
            break
        rows = [r for r in rows if r[0] <= end_ms]
        total += upsert_candles(market_symbol, timeframe, rows)
        if not rows or rows[-1][0] == since:
            break  # no forward progress; avoid an infinite loop
        since = rows[-1][0] + 1

    return total


def update_recent(market_symbol: MarketSymbol, timeframe: str, exchange=None) -> int:
    """Incremental update: fetch from the last known candle (or a short lookback) to now."""
    exchange = exchange or get_spot_exchange()
    last = (
        Candle.objects.filter(symbol=market_symbol, timeframe=timeframe)
        .order_by("-timestamp")
        .first()
    )
    interval = timedelta(seconds=exchange.parse_timeframe(timeframe))
    start = last.timestamp if last else timezone.now() - interval * 2
    return fetch_historical(market_symbol, timeframe, start, timezone.now(), exchange=exchange)


def fetch_funding_rates(market_symbol: MarketSymbol, start, end, exchange=None) -> int:
    exchange = exchange or get_futures_exchange()
    ccxt_symbol = swap_ccxt_symbol(market_symbol)
    since = _ms(start)
    end_ms = _ms(end)
    total = 0

    while since <= end_ms:
        rows = call_with_retry(
            exchange.fetch_funding_rate_history, ccxt_symbol, since=since, limit=PAGE_LIMIT
        )
        if not rows:
            break
        rows = [r for r in rows if r["timestamp"] <= end_ms]
        for row in rows:
            FundingRate.objects.update_or_create(
                symbol=market_symbol,
                timestamp=_from_ms(row["timestamp"]),
                defaults={"funding_rate": row["fundingRate"]},
            )
        total += len(rows)
        if not rows or rows[-1]["timestamp"] == since:
            break
        since = rows[-1]["timestamp"] + 1

    return total


def fetch_open_interest(market_symbol: MarketSymbol, timeframe: str = "1h", exchange=None) -> int:
    """Binance's public API only exposes recent open-interest history (~30 days)."""
    exchange = exchange or get_futures_exchange()
    ccxt_symbol = swap_ccxt_symbol(market_symbol)

    rows = call_with_retry(
        exchange.fetch_open_interest_history, ccxt_symbol, timeframe=timeframe, limit=PAGE_LIMIT
    )
    for row in rows or []:
        OpenInterest.objects.update_or_create(
            symbol=market_symbol,
            timestamp=_from_ms(row["timestamp"]),
            defaults={"open_interest": row["openInterestAmount"]},
        )
    return len(rows or [])


def get_symbol_stats(symbol_code: str, timeframe: str) -> dict:
    """Summary used by the dashboard's market-data card."""
    try:
        market_symbol = MarketSymbol.objects.get(symbol=symbol_code)
    except MarketSymbol.DoesNotExist:
        return None

    candles = Candle.objects.filter(symbol=market_symbol, timeframe=timeframe)
    first = candles.order_by("timestamp").first()
    last = candles.order_by("-timestamp").first()
    missing_count = (
        len(find_missing_candles(market_symbol, timeframe, first.timestamp, last.timestamp))
        if first and last
        else 0
    )

    return {
        "symbol": symbol_code,
        "timeframe": timeframe,
        "first_candle": first.timestamp if first else None,
        "last_candle": last.timestamp if last else None,
        "candle_count": candles.count(),
        "missing_candle_count": missing_count,
        "funding_count": FundingRate.objects.filter(symbol=market_symbol).count(),
        "open_interest_count": OpenInterest.objects.filter(symbol=market_symbol).count(),
    }


def find_missing_candles(market_symbol: MarketSymbol, timeframe: str, start, end) -> list:
    """Compare the expected candle grid against what's stored. Reports gaps, never fills them."""
    interval = timedelta(seconds=get_spot_exchange().parse_timeframe(timeframe))
    existing = set(
        Candle.objects.filter(
            symbol=market_symbol, timeframe=timeframe, timestamp__gte=start, timestamp__lte=end
        ).values_list("timestamp", flat=True)
    )

    missing = []
    cursor = start
    while cursor <= end:
        if cursor not in existing:
            missing.append(cursor)
        cursor += interval
    return missing
