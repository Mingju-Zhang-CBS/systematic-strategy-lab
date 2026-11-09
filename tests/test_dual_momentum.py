import numpy as np
import pandas as pd
import pytest

from strategy_lab import dual_momentum as dm


def test_cash_controls_use_strict_gate_and_only_previous_decisions():
    months = pd.period_range("2007-06", periods=50, freq="M")
    returns = pd.DataFrame(0.0, index=months, columns=dm.COLUMNS)
    returns.iloc[:47, returns.columns.get_loc("SPY")] = 0.02
    returns.loc[months[47], "SPY"] = -0.9
    targets = dm.target_weights(returns)
    signal = months[47]
    assert targets["relative"].at[signal, "EFA"] == 0.25
    assert targets["trailing36"].at[signal, "EFA"] == 0.25
    assert targets["trailing36"].at[months[48], "EFA"] == pytest.approx(0.25 * 35 / 36)
    assert targets["dual"].at[signal, "RF"] == 1.0
    assert targets["same_gate_equal"].at[signal, "RF"] == 1.0
    assert targets["same_gate_equal"].at[months[46], "EFA"] == 0.125


def test_next_close_uses_old_positions_and_funds_both_trade_legs():
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04"])
    daily = pd.DataFrame(0.0, index=dates, columns=dm.COLUMNS)
    daily["SPY"] = [0.9, 0.1, 0.2, 0.9]
    daily["EFA"] = [0.0, 0.0, 0.6, 0.1]
    quotes = pd.DataFrame(10.0, index=dates, columns=dm.ASSETS)
    targets = pd.DataFrame(0.0, index=pd.period_range("2019-12", periods=2, freq="M"), columns=dm.COLUMNS)
    targets.iloc[0, 0] = targets.iloc[1, 1] = 1.0
    ledger = dm.simulate(daily, quotes, targets, 10, "2020-01", "2020-02")
    initial = 1 / 1.001
    pre_second = initial * 1.1 * 1.2
    second = pre_second * 0.999 / 1.001
    assert ledger.nav.to_list() == pytest.approx([initial, initial * 1.1, second, second * 1.1])
    assert ledger.turnover.iloc[2] == pytest.approx(1 + second / pre_second)
    assert ledger.fee.iloc[2] == pytest.approx(0.001 * ledger.turnover.iloc[2])
    quotes.iloc[2, 0] = np.nan
    with pytest.raises(ValueError, match="scheduled execution"):
        dm.simulate(daily, quotes, targets, 10, "2020-01", "2020-02")


def test_cash_compounding_and_paired_identical_paths():
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03"])
    etfs = pd.DataFrame(0.0, index=dates, columns=dm.ASSETS)
    rf = pd.Series([0.02, 0.01], index=pd.period_range("2020-01", periods=2, freq="M"))
    monthly = dm.monthly_marks(dm.session_returns(etfs, rf))["RF"]
    assert monthly.to_list() == pytest.approx(rf.to_list())
    assert dm.paired_log_growth(monthly, monthly, block=2) == {"estimate": 0, "low": 0, "high": 0}
