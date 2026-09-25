from datetime import datetime, timezone as dt_timezone

from core.execution.scheduling import current_candle_open, latest_closed_candle_open, next_candle_close


def test_current_candle_open_floors_to_the_hour():
    now = datetime(2024, 1, 1, 14, 37, 22, tzinfo=dt_timezone.utc)
    assert current_candle_open(now, "1h") == datetime(2024, 1, 1, 14, 0, tzinfo=dt_timezone.utc)


def test_latest_closed_candle_is_one_interval_before_current():
    now = datetime(2024, 1, 1, 14, 5, tzinfo=dt_timezone.utc)
    assert latest_closed_candle_open(now, "1h") == datetime(2024, 1, 1, 13, 0, tzinfo=dt_timezone.utc)


def test_next_candle_close_is_the_current_candles_end():
    now = datetime(2024, 1, 1, 14, 5, tzinfo=dt_timezone.utc)
    assert next_candle_close(now, "1h") == datetime(2024, 1, 1, 15, 0, tzinfo=dt_timezone.utc)


def test_15m_and_4h_intervals():
    now = datetime(2024, 1, 1, 14, 37, tzinfo=dt_timezone.utc)
    assert current_candle_open(now, "15m") == datetime(2024, 1, 1, 14, 30, tzinfo=dt_timezone.utc)
    assert current_candle_open(now, "4h") == datetime(2024, 1, 1, 12, 0, tzinfo=dt_timezone.utc)
