import numpy as np
import pandas as pd
import pytest

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_walkforward as wf


def test_selection_uses_only_prior_months_and_routes_december_target_to_january():
    index = pd.period_range("2012-01", "2018-12", freq="M")
    swing = 0.01 * np.sin(np.arange(len(index)))
    returns = pd.DataFrame({
        "floor_25": swing + 0.001,
        "floor_50": swing + 0.004,
        "floor_75": swing + 0.002,
    }, index=index)
    rf = pd.Series(0.0, index=index)
    schedule = wf.folds(returns, rf, test_end="2018-06")
    assert schedule.loc[2017, "train_last"] == pd.Period("2016-12", "M")
    assert schedule.loc[2017, "train_first"] == pd.Period("2012-01", "M")
    assert schedule.loc[2017, "selected"] == "floor_50"
    assert schedule.loc[2018, "test_last"] == pd.Period("2018-06", "M")
    changed = returns.copy()
    changed.loc["2017-01":, "floor_50"] -= 0.02
    next_schedule = wf.folds(changed, rf, test_end="2018-06")
    pd.testing.assert_series_equal(next_schedule.loc[2017], schedule.loc[2017])
    assert next_schedule.loc[2018, "selected"] == "floor_75"

    candidates = {arm: pd.DataFrame({"SPY": value}, index=index) for arm, value in wf.FLOORS.items()}
    targets = wf.selected_targets(candidates, next_schedule)
    assert targets.at[pd.Period("2017-11", "M"), "SPY"] == 0.50
    assert targets.at[pd.Period("2017-12", "M"), "SPY"] == 0.75
    assert targets.at[pd.Period("2018-05", "M"), "SPY"] == 0.75
    assert targets.at[pd.Period("2018-06", "M"), "SPY"] == 0.50


def test_closed_sleeve_sizes_and_rebasing_keep_prior_nav():
    months = pd.period_range("2016-12", periods=2, freq="M")
    relative = pd.DataFrame(0.0, index=months, columns=dm.COLUMNS)
    relative["SPY"], relative["RF"] = 0.25, 0.75
    dual = relative.copy()
    dual.loc[months[0], ["SPY", "RF"]] = [0, 1]
    targets = wf.fixed_targets({"relative": relative, "dual": dual})
    for arm, fraction in wf.FLOORS.items():
        assert targets[arm]["SPY"].tolist() == [0.25 * fraction, 0.25]
        assert targets[arm].sum(axis=1).eq(1).all()
    dates = pd.to_datetime(["2016-12-30", "2017-01-03", "2017-01-04"])
    ledger = pd.DataFrame({"nav": [2.0, 1.8, 2.2], "return": [0, -0.1, 2.2 / 1.8 - 1]}, index=dates)
    sample = wf.holdout_ledger(ledger)
    assert sample.nav.tolist() == pytest.approx([0.9, 1.1])
    assert sample["return"].iloc[0] == -0.1


def test_cash_spell_fragments_split_at_fold_boundary_before_classification():
    dates = pd.to_datetime(["2017-12-28", "2017-12-29", "2018-01-02", "2018-01-03"])
    daily = pd.DataFrame(0.0, index=dates, columns=dm.COLUMNS)
    daily["SPY"] = [0.0, 0.10, -0.05, -0.10]
    fractions = {"dual": 0, "relative": 1, **wf.FLOORS, wf.ADAPTIVE: 0.50}
    accounts = {}
    for arm, fraction in fractions.items():
        weights = np.zeros((len(dates), 8))
        weights[1:, 0] = 0.25 * fraction
        accounts[arm] = {"weights": weights, "fees": np.zeros_like(weights), "r": weights[:, 0] * daily.SPY.to_numpy()}
    fragments = wf.cash_spell_fragments(daily, accounts)
    assert len(fragments) == 8
    assert fragments.loc[fragments.year.eq(2017), "sessions"].eq(1).all()
    assert fragments.loc[fragments.year.eq(2018), "sessions"].eq(2).all()
    pooled, years = wf.fragment_summary(fragments, [2017, 2018, 2019])
    assert years[2017]["floor_50"]["protection_retained_fraction"] is None
    assert years[2018]["floor_50"]["miss_capture_fraction"] is None
    assert years[2019] == {}
    assert pooled["floor_25"]["miss_capture_fraction"] < pooled["floor_50"]["miss_capture_fraction"]
    assert pooled["floor_75"]["protection_retained_fraction"] < pooled["floor_50"]["protection_retained_fraction"]
