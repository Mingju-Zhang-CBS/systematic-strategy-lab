import pandas as pd
import pytest

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr
from strategy_lab import dual_momentum_rebound as rb


def test_floor_and_fast_gate_keep_ranking_and_preserve_first_exit():
    index = pd.period_range("2019-01", periods=18, freq="M")
    data = pd.DataFrame(0.0, index=index, columns=dm.COLUMNS)
    data["RF"] = 0.001
    data["SPY"] = 0.02
    data.loc[index[12], ["SPY", "EFA"]] = [-0.28, -0.30]
    data.loc[index[16], "SPY"] = -0.09
    original = dm.target_weights(data)
    targets = rb.variant_targets(data, original)
    half, fast = targets["half_risk"], targets["reentry_3m"]
    assert original["dual"].loc[index[11:17], "SPY"].tolist() == [0.25, 0, 0, 0, 0, 0]
    assert half.loc[index[11:17], "SPY"].tolist() == [0.25, 0.125, 0.125, 0.125, 0.125, 0.125]
    assert fast.loc[index[11:17], "SPY"].tolist() == [0.25, 0, 0, 0, 0.25, 0]
    assert fast["EFA"].eq(0).all()
    for frame in targets.values():
        assert frame.sum(axis=1).eq(1).all()
    changed = data.copy()
    changed.loc[index[16]:, "SPY"] = 0.7
    rerun = rb.variant_targets(changed, dm.target_weights(changed))
    for arm in rb.VARIANTS:
        pd.testing.assert_frame_equal(targets[arm].loc[:index[15]], rerun[arm].loc[:index[15]])


def test_cash_spell_attribution_uses_old_holdings_until_next_close():
    index = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-03-02", "2020-03-03"])
    daily = pd.DataFrame(0.0, index=index, columns=dm.COLUMNS)
    daily["SPY"] = [0.0, 0.02, 0.90, 0.10, 0.20, 0.80]
    closes = pd.DataFrame(10.0, index=index, columns=dm.ASSETS)
    months = pd.period_range("2019-12", periods=3, freq="M")
    full = pd.DataFrame(0.0, index=months, columns=dm.COLUMNS)
    full["SPY"], full["RF"] = 0.25, 0.75
    dual = full.copy()
    dual.loc[months[1], ["SPY", "RF"]] = [0.0, 1.0]
    accounts = {}
    for arm, target in {"relative": full, "dual": dual, "half_risk": (full + dual) / 2, "reentry_3m": dual}.items():
        ledger = dm.simulate(daily, closes, target, 10, "2020-01", "2020-03")
        accounts[arm] = attr.replay(daily, closes, target, ledger)
    linked, off = attr.components(accounts["dual"], accounts["relative"], daily[list(dm.ASSETS)].to_numpy(), index)
    spells = attr.cash_spells(index, accounts["dual"], accounts["relative"], linked, off)
    effects = rb.compare_cash_spells(daily, accounts, spells)
    half, fast = effects.itertuples(index=False)
    assert half.first_variant_risk_close == index[2]
    assert 0 < half.variant_exposure_vs_dual_pp < -half.original_cash_effect_pp
    assert pd.isna(fast.first_variant_risk_close)
    assert fast.variant_exposure_vs_dual_pp == pytest.approx(0)
    assert rb.spell_summary(effects)["half_risk"]["protection_retained_fraction"] is None
