"""Monthly windows for the same funded trailing-volatility calibration."""

import pandas as pd

from . import dual_momentum_volmatch as vm
from . import dual_momentum_walkforward as wf
from . import dual_momentum as dm


def monthly_windows(first=wf.TEST_START, last=dm.END):
    """Each test month is preceded by exactly 60 completed training months."""
    months = pd.period_range(first, last, freq="M")
    if months.empty:
        raise ValueError("Empty monthly test window")
    return pd.DataFrame({
        "train_first": months - wf.TRAIN_MONTHS,
        "train_last": months - 1,
        "test_first": months,
        "test_last": months,
    })


def calibrate(daily, closes, candidates, rf):
    schedule = vm.calibrate(daily, closes, candidates, rf, monthly_windows())
    schedule.index = pd.PeriodIndex(schedule.test_first, freq="M", name="test_month")
    return schedule
