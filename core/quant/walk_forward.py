"""Walk-forward window generation. Pure date math, no DB -- given an overall
date range and a mode, produces the sequence of (train, test) windows.

No leakage by construction: every window's test_start is exactly train_end +
1 day, so a window's own training data can never include its own test period,
regardless of mode.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class Window:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


def generate_windows(
    start: datetime,
    end: datetime,
    mode: str,
    training_months: int = 24,
    test_months: int = 3,
    retrain_months: int = 3,
) -> list[Window]:
    """mode: "rolling" (fixed-width training window that slides forward) or
    "expanding" (training window always starts at `start` and grows). Stops
    once no test data remains before `end`; the final window's test period is
    truncated to `end` rather than dropped, to use whatever data is available.
    """
    if mode not in ("rolling", "expanding"):
        raise ValueError(f"unknown walk-forward mode: {mode!r}")

    windows = []
    index = 0
    test_start = start + relativedelta(months=training_months)

    while test_start <= end:
        train_end = test_start - ONE_DAY
        train_start = (
            start if mode == "expanding" else train_end - relativedelta(months=training_months) + ONE_DAY
        )
        test_end = min(test_start + relativedelta(months=test_months) - ONE_DAY, end)

        windows.append(Window(index, train_start, train_end, test_start, test_end))
        index += 1
        test_start = test_start + relativedelta(months=retrain_months)

    return windows
