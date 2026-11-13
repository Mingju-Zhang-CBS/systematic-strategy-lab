"""Match trailing funded volatility for the 75% floor and past exposure."""

import numpy as np
import pandas as pd

from . import dual_momentum as dm
from . import dual_momentum_attribution as attr
from . import dual_momentum_walkforward as wf

BASES = ("floor_75", "trailing36")
MATCHED = ("floor_75_matched", "trailing36_matched")
WINDOW_COLUMNS = ("train_first", "train_last", "test_first", "test_last")
VOL_TOL = 1e-8


def scaled_targets(target, scale):
    """Shrink the ETF weights and allocate the residual to the same cash proxy."""
    risky = target[list(dm.ASSETS)].mul(scale, axis=0)
    return risky.assign(RF=1 - risky.sum(axis=1))


def funded_vol(daily, closes, target, rf, first, last, scale):
    """Replay a fixed scale on the training interval and one positioning month."""
    warmup, stop = str(first - 1), str(last)
    ledger = dm.simulate(
        daily.loc[warmup:stop], closes.loc[warmup:stop],
        scaled_targets(target.loc[first - 2:last - 1], scale), attr.PRIMARY_COST,
        start=warmup, end=stop,
    )
    monthly = dm.monthly_marks(ledger["return"]).loc[first:last]
    if not monthly.index.equals(pd.period_range(first, last, freq="M")):
        raise ValueError("Incomplete training returns")
    excess = monthly - rf.reindex(monthly.index)
    volatility = float(np.sqrt(12) * excess.std())
    if not np.isfinite(volatility):
        raise ValueError("Training volatility is not finite")
    return volatility


def fit_scale(vol_at_scale, unscaled, common):
    """Find a funded, unlevered allocation that reaches the common training risk."""
    if not 0 < common <= unscaled:
        raise ValueError("Common volatility must be positive and no higher than unscaled")
    if common == unscaled:
        return 1.0, unscaled
    low, high = 0.0, 1.0
    for _ in range(30):
        scale = (low + high) / 2
        vol = vol_at_scale(scale)
        if abs(vol - common) <= VOL_TOL:
            return scale, vol
        if vol < common:
            low = scale
        else:
            high = scale
    raise ArithmeticError("Could not match training volatility")


def calibrate(daily, closes, candidates, rf, windows, train_months=wf.TRAIN_MONTHS):
    """Use the archived fold boundaries to calibrate risk before the holdout."""
    if not isinstance(train_months, int) or train_months < 2:
        raise ValueError("Training window must contain at least two completed months")
    rows = []
    for window in windows.itertuples():
        first, last = window.train_first, window.train_last
        if (
            last != window.test_first - 1
            or first != window.test_first - train_months
            or window.test_first > window.test_last
        ):
            raise ValueError("Training and test windows do not match the archived clock")
        vols = {arm: funded_vol(daily, closes, candidates[arm], rf, first, last, 1.0) for arm in BASES}
        common = min(vols.values())
        row = {name: getattr(window, name) for name in WINDOW_COLUMNS}
        row.update(year=int(window.Index), common_vol=common)
        for arm in BASES:
            def vol_at_scale(scale):
                return funded_vol(daily, closes, candidates[arm], rf, first, last, scale)

            scale, realized = fit_scale(vol_at_scale, vols[arm], common)
            row.update({f"{arm}_unscaled_vol": vols[arm], f"{arm}_scale": scale, f"{arm}_fitted_vol": realized})
        rows.append(row)
    return pd.DataFrame(rows).set_index("year")


def apply_schedule(candidates, schedule):
    """Use the calibrated scale for all targets executed in the next test fold."""
    result = {}
    for arm, label in zip(BASES, MATCHED, strict=True):
        target = candidates[arm]
        scales = pd.Series(1.0, index=target.index)
        for row in schedule.itertuples():
            signals = pd.period_range(row.test_first - 1, row.test_last - 1, freq="M")
            scales.loc[signals] = getattr(row, f"{arm}_scale")
        result[label] = scaled_targets(target, scales)
    return result


def period_risk(ledger, rf, first, last):
    """Summarize an untouched account segment with prior-close NAV as its anchor."""
    sample = wf.holdout_ledger(ledger, str(first)).loc[:str(last)]
    monthly = dm.monthly_marks(sample["return"])
    excess = monthly - rf.reindex(monthly.index)
    return {
        "net": float(sample.nav.iloc[-1] - 1),
        "excess_vol": float(np.sqrt(12) * excess.std()),
        "daily_max_drawdown": dm.max_drawdown(sample.nav),
    }
