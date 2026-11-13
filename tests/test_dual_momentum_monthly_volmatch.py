import numpy as np
import pandas as pd

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_volmatch as vm
from strategy_lab import dual_momentum_monthly_volmatch as monthly


def test_monthly_windows_use_only_previous_60_completed_months():
    windows = monthly.monthly_windows()
    assert len(windows) == 114
    assert windows.iloc[0].train_first == pd.Period("2012-01", "M")
    assert windows.iloc[0].train_last == pd.Period("2016-12", "M")
    assert windows.iloc[1].train_first == pd.Period("2012-02", "M")
    assert windows.iloc[-1].test_first == pd.Period("2026-06", "M")
    assert windows.test_first.equals(windows.test_last)
    assert (windows.train_last == windows.test_first - 1).all()


def test_new_month_observation_changes_only_later_calibration(monkeypatch):
    periods = pd.period_range("2011-12", "2017-02", freq="M")
    dates = pd.DatetimeIndex([
        day for period in periods
        for day in pd.bdate_range(period.start_time, period.end_time)[[0, -1]]
    ])
    daily = pd.DataFrame(0.0, index=dates, columns=dm.COLUMNS)
    daily["SPY"] = 0.02 * np.sin(np.arange(len(dates)) * 0.9)
    closes = pd.DataFrame(10.0, index=dates, columns=dm.ASSETS)
    signal_months = pd.period_range("2011-11", "2017-01", freq="M")
    candidates = {}
    for arm, size in zip(vm.BASES, [0.75, 0.50], strict=True):
        weights = pd.DataFrame(0.0, index=signal_months, columns=dm.COLUMNS)
        weights["SPY"], weights["RF"] = size, 1 - size
        candidates[arm] = weights
    rf = pd.Series(0.0, index=periods)
    windows = monthly.monthly_windows("2017-01", "2017-02")
    monkeypatch.setattr(monthly, "monthly_windows", lambda: windows)
    before = monthly.calibrate(daily, closes, candidates, rf)
    changed = daily.copy()
    changed.loc[changed.index.to_period("M") == pd.Period("2017-01", "M"), "SPY"] = 0.80
    after = monthly.calibrate(changed, closes, candidates, rf)
    pd.testing.assert_series_equal(before.loc["2017-01"], after.loc["2017-01"])
    assert before.loc["2017-02", "common_vol"] != after.loc["2017-02", "common_vol"]
    assert (after.floor_75_fitted_vol - after.trailing36_fitted_vol).abs().max() <= vm.VOL_TOL

    targets = vm.apply_schedule(candidates, before)
    jan_signal = pd.Period("2016-12", "M")
    feb_signal = pd.Period("2017-01", "M")
    assert targets["floor_75_matched"].at[jan_signal, "SPY"] == 0.75 * before.loc["2017-01", "floor_75_scale"]
    assert targets["floor_75_matched"].at[feb_signal, "SPY"] == 0.75 * before.loc["2017-02", "floor_75_scale"]
