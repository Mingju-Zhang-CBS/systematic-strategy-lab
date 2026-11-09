import numpy as np
import pandas as pd
import pytest

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_volmatch as vm


def test_scale_calibration_reaches_common_risk_without_leverage():
    scale, vol = vm.fit_scale(lambda x: 0.14 * x**1.1, 0.14, 0.09)
    assert 0 < scale < 1
    assert vol == pytest.approx(0.09, abs=vm.VOL_TOL)
    assert vm.fit_scale(lambda _: pytest.fail("An unchanged arm needs no replay"), 0.09, 0.09) == (1, 0.09)
    with pytest.raises(ValueError, match="no higher"):
        vm.fit_scale(lambda x: 0.09 * x, 0.09, 0.14)


def test_training_replay_is_funded_and_ignores_future_returns():
    sessions = pd.bdate_range("2016-12-01", "2017-04-28")
    daily = pd.DataFrame(0.0, index=sessions, columns=dm.COLUMNS)
    daily.loc["2017-01-10", "SPY"] = 0.10
    daily.loc["2017-02-10", "SPY"] = -0.08
    daily.loc["2017-03-10", "SPY"] = 0.06
    quotes = pd.DataFrame(10.0, index=sessions, columns=dm.ASSETS)
    signals = pd.period_range("2016-11", "2017-03", freq="M")
    target = pd.DataFrame(0.0, index=signals, columns=dm.COLUMNS)
    target["SPY"], target["RF"] = 0.75, 0.25
    months = pd.period_range("2016-12", "2017-04", freq="M")
    rf = pd.Series(0.0, index=months)
    first, last = pd.Period("2017-01", "M"), pd.Period("2017-03", "M")
    unscaled = vm.funded_vol(daily, quotes, target, rf, first, last, 1.0)
    half = vm.funded_vol(daily, quotes, target, rf, first, last, 0.50)
    assert 0 < half < unscaled
    ledger = dm.simulate(daily, quotes, vm.scaled_targets(target, 0.50), 10, start="2016-12", end="2017-03")
    reconstructed = np.sqrt(12) * dm.monthly_marks(ledger["return"]).loc[first:last].std()
    assert half == pytest.approx(reconstructed, abs=1e-13)
    daily.loc["2017-04", "SPY"] = 0.75
    assert vm.funded_vol(daily, quotes, target, rf, first, last, 0.50) == half


def test_schedule_changes_december_signal_for_january_trade_and_keeps_cash_funded():
    months = pd.period_range("2016-11", "2017-02", freq="M")
    target = pd.DataFrame(0.0, index=months, columns=dm.COLUMNS)
    target["SPY"], target["RF"] = 0.75, 0.25
    schedule = pd.DataFrame({
        "test_first": [pd.Period("2017-01", "M")],
        "test_last": [pd.Period("2017-02", "M")],
        "floor_75_scale": [0.80],
        "trailing36_scale": [1.0],
    })
    matched = vm.apply_schedule(dict.fromkeys(vm.BASES, target), schedule)
    floor = matched["floor_75_matched"]
    assert floor["SPY"].tolist() == pytest.approx([0.75, 0.60, 0.60, 0.75])
    assert floor.RF.tolist() == pytest.approx([0.25, 0.40, 0.40, 0.25])
    pd.testing.assert_frame_equal(matched["trailing36_matched"], target)
