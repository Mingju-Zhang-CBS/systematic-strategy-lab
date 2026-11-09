import numpy as np
import pandas as pd
import pytest

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr


def test_cash_mix_fees_link_to_exact_daily_log_gap():
    index = pd.date_range("2020-01-01", periods=2)
    excess = np.zeros((2, 8))
    excess[:, :2] = [0.12, -0.04]
    dw = np.zeros_like(excess)
    cw = np.zeros_like(excess)
    dw[1, 0] = 0.25
    cw[0, 0] = 0.25
    cw[1, :2] = 0.125
    fee = np.zeros_like(excess)
    fee[1, 0] = 0.0004
    dual = {"weights": dw, "fees": fee, "r": (dw * excess - fee).sum(axis=1)}
    control = {"weights": cw, "fees": np.zeros_like(fee), "r": (cw * excess).sum(axis=1)}
    linked, off = attr.components(dual, control, excess, index)
    equity = linked["SPY/EFA"]
    assert off[:, 0].tolist() == [True, False]
    assert equity.cash_off.iloc[0] == pytest.approx(-np.log1p(0.03))
    assert equity.selection.iloc[0] == 0
    assert equity.active_exposure.iloc[1] == 0
    assert equity.selection.iloc[1] > 0
    assert equity.fees.iloc[1] < 0
    np.testing.assert_allclose(linked.sum(axis=1), np.log1p(dual["r"]) - np.log1p(control["r"]))


def test_cash_spell_earns_old_holdings_through_reentry_close():
    index = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-03-02", "2020-03-03"])
    daily = pd.DataFrame(0.0, index=index, columns=dm.COLUMNS)
    daily["SPY"] = [0.0, 0.05, -0.06, 0.10, 0.20, 0.01]
    closes = pd.DataFrame(10.0, index=index, columns=dm.ASSETS)
    months = pd.period_range("2019-12", periods=3, freq="M")
    relative = pd.DataFrame(0.0, index=months, columns=dm.COLUMNS)
    relative["SPY"], relative["RF"] = 0.25, 0.75
    dual = relative.copy()
    dual.loc["2020-01", ["SPY", "RF"]] = [0.0, 1.0]
    accounts = []
    for target in (dual, relative):
        ledger = dm.simulate(daily, closes, target, 10, "2020-01", "2020-03")
        accounts.append(attr.replay(daily, closes, target, ledger))
    linked, off = attr.components(*accounts, daily[list(dm.ASSETS)].to_numpy(), index)
    event = attr.cash_spells(index, *accounts, linked, off).iloc[0]
    assert event.cash_from_close == index[2]
    assert event.through_close == index[4]
    assert event.sessions == 2
    assert event.sold == event.reentry == event.relative_held == "SPY"
    assert event.cash_off_log_pp < 0
    assert linked["SPY/EFA", "cash_off"].iloc[[2, 5]].eq(0).all()
