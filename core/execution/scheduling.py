"""Candle-close-driven scheduling: pure time math, no DB, no exchange calls.
Only the timeframes EngineConfig actually supports are covered.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}


def current_candle_open(now: datetime, timeframe: str) -> datetime:
    """The open time of the candle that's still forming right now."""
    interval = TIMEFRAME_SECONDS[timeframe]
    epoch_seconds = int(now.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval)
    return datetime.fromtimestamp(floored, tz=dt_timezone.utc)


def latest_closed_candle_open(now: datetime, timeframe: str) -> datetime:
    """The open time of the most recently CLOSED candle -- the one that should
    be evaluated once it's actually in the DB with closed=True."""
    return current_candle_open(now, timeframe) - timedelta(seconds=TIMEFRAME_SECONDS[timeframe])


def next_candle_close(now: datetime, timeframe: str) -> datetime:
    """When the currently-forming candle will close -- i.e. the next time a
    new evaluation is expected."""
    return current_candle_open(now, timeframe) + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
