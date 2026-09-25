from datetime import datetime, timezone as dt_timezone

import pytest

from core.quant.walk_forward import generate_windows

START = datetime(2021, 1, 1, tzinfo=dt_timezone.utc)


def test_matches_the_documented_rolling_example():
    end = datetime(2023, 12, 31, tzinfo=dt_timezone.utc)
    windows = generate_windows(START, end, "rolling")

    assert windows[0].train_start == datetime(2021, 1, 1, tzinfo=dt_timezone.utc)
    assert windows[0].train_end == datetime(2022, 12, 31, tzinfo=dt_timezone.utc)
    assert windows[0].test_start == datetime(2023, 1, 1, tzinfo=dt_timezone.utc)
    assert windows[0].test_end == datetime(2023, 3, 31, tzinfo=dt_timezone.utc)

    assert windows[1].train_start == datetime(2021, 4, 1, tzinfo=dt_timezone.utc)  # slid forward 3mo
    assert windows[1].train_end == datetime(2023, 3, 31, tzinfo=dt_timezone.utc)
    assert windows[1].test_start == datetime(2023, 4, 1, tzinfo=dt_timezone.utc)
    assert windows[1].test_end == datetime(2023, 6, 30, tzinfo=dt_timezone.utc)


def test_expanding_mode_never_moves_train_start():
    end = datetime(2023, 12, 31, tzinfo=dt_timezone.utc)
    windows = generate_windows(START, end, "expanding")

    assert all(w.train_start == START for w in windows)
    assert windows[1].train_end == datetime(2023, 3, 31, tzinfo=dt_timezone.utc)  # still grows like rolling


def test_no_window_can_see_its_own_future():
    end = datetime(2023, 12, 31, tzinfo=dt_timezone.utc)
    for mode in ("rolling", "expanding"):
        for w in generate_windows(START, end, mode):
            assert w.train_end < w.test_start
            assert w.train_start <= w.train_end
            assert w.test_start <= w.test_end


def test_stops_at_available_data_and_truncates_last_window():
    end = datetime(2023, 4, 15, tzinfo=dt_timezone.utc)  # mid-way through what would be window 1's test period
    windows = generate_windows(START, end, "rolling")

    assert len(windows) == 2
    assert windows[-1].test_end == end  # truncated, not dropped


def test_rejects_unknown_mode():
    with pytest.raises(ValueError):
        generate_windows(START, datetime(2022, 1, 1, tzinfo=dt_timezone.utc), "sideways")
