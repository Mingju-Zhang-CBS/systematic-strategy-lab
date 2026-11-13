"""Monthly windows for the same funded trailing-volatility calibration."""

import pandas as pd

from . import dual_momentum_volmatch as vm
from . import dual_momentum_walkforward as wf
from . import dual_momentum as dm


def monthly_windows(first=wf.TEST_START, last=dm.END, train_months=wf.TRAIN_MONTHS):
    """Each test month follows a fixed count of completed training months."""
    if not isinstance(train_months, int) or train_months < 2:
        raise ValueError("Training window must contain at least two completed months")
    months = pd.period_range(first, last, freq="M")
    if months.empty:
        raise ValueError("Empty monthly test window")
    return pd.DataFrame({
        "train_first": months - train_months,
        "train_last": months - 1,
        "test_first": months,
        "test_last": months,
    })


def calibrate(daily, closes, candidates, rf, train_months=wf.TRAIN_MONTHS):
    schedule = vm.calibrate(
        daily, closes, candidates, rf, monthly_windows(train_months=train_months),
        train_months=train_months,
    )
    schedule.index = pd.PeriodIndex(schedule.test_first, freq="M", name="test_month")
    return schedule
