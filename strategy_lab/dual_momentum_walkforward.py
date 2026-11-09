"""Rolling annual holdouts for fixed and adaptively selected closed-gate floors."""

import numpy as np
import pandas as pd

from . import dual_momentum as dm
from . import dual_momentum_attribution as attr
from . import dual_momentum_rebound as rebound

FLOORS = {"floor_25": 0.25, "floor_50": 0.50, "floor_75": 0.75}
PREFERENCE = ("floor_50", "floor_25", "floor_75")
ADAPTIVE = "annual_selected"
TEST_START = "2017-01"
TRAIN_MONTHS = 60


def fixed_targets(original):
    relative, dual = original["relative"], original["dual"]
    return {arm: retained * relative + (1 - retained) * dual for arm, retained in FLOORS.items()}


def folds(monthly_net, rf, test_start=TEST_START, test_end=dm.END, train_months=TRAIN_MONTHS):
    """Choose a floor before each January using strictly earlier monthly observations."""
    start, end = pd.Period(test_start, "M"), pd.Period(test_end, "M")
    if start.month != 1 or end < start or train_months < 2:
        raise ValueError("Expected annual folds with a valid training window")
    rows = []
    for year in range(start.year, end.year + 1):
        test_first = pd.Period(f"{year}-01", "M")
        test_last = min(pd.Period(f"{year}-12", "M"), end)
        train = pd.period_range(test_first - train_months, test_first - 1, freq="M")
        sample = monthly_net.loc[:, list(PREFERENCE)].reindex(train).sub(rf.reindex(train), axis=0)
        if not np.isfinite(sample).all().all():
            raise ValueError("Missing month in a floor selection window")
        vol = sample.std()
        if not vol.gt(0).all():
            raise ValueError("Selection requires finite positive training volatility")
        scores = np.sqrt(12) * sample.mean() / vol
        rows.append({
            "year": year, "train_first": train[0], "train_last": train[-1],
            "test_first": test_first, "test_last": test_last,
            "selected": scores.idxmax(), **scores.to_dict(),
        })
    return pd.DataFrame(rows).set_index("year")


def selected_targets(candidates, schedule):
    """Use the December signal for the January trade and carry one account."""
    result = candidates["floor_50"].copy()
    for row in schedule.itertuples():
        signals = pd.period_range(row.test_first - 1, row.test_last - 1, freq="M")
        result.loc[signals] = candidates[row.selected].loc[signals]
    return result


def holdout_ledger(ledger, start=TEST_START):
    """Rebase test NAV at the prior close without restarting positions or costs."""
    sample = ledger.loc[start:].copy()
    if sample.empty:
        raise ValueError("Missing holdout history")
    anchor = ledger.loc[ledger.index < sample.index[0], "nav"]
    if anchor.empty:
        raise ValueError("No pre-holdout close for carried account")
    sample["nav"] /= anchor.iloc[-1]
    return sample


def cash_spell_fragments(daily, accounts, start=TEST_START):
    """Slice original off-gate spells into forward-fold fragments and link effects."""
    index = daily.index
    excess = daily[list(dm.ASSETS)].sub(daily.RF, axis=0).to_numpy(dtype=float)
    dual, relative = accounts["dual"], accounts["relative"]
    original, off = attr.components(dual, relative, excess, index)
    effects = {
        arm: attr.components(accounts[arm], dual, excess, index)[0]
        for arm in (*FLOORS, ADAPTIVE)
    }
    in_test = index.to_period("M") >= pd.Period(start, "M")
    rows = []
    for j, sleeve in enumerate(attr.SLEEVES):
        positions = np.flatnonzero(off[:, j] & in_test)
        breaks = (np.diff(positions) != 1) | (np.diff(index.year.to_numpy()[positions]) != 0)
        for fragment in np.split(positions, np.flatnonzero(breaks) + 1):
            if not len(fragment):
                continue
            first, last = index[fragment[[0, -1]]]
            baseline = 100 * original[sleeve, "cash_off"].iloc[fragment].sum()
            for arm, frame in effects.items():
                rows.append({
                    "year": int(first.year), "sleeve": sleeve, "arm": arm,
                    "first_session": first, "last_session": last, "sessions": len(fragment),
                    "original_cash_effect_pp": baseline,
                    "variant_exposure_vs_dual_pp": 100 * frame[sleeve, "active_exposure"].iloc[fragment].sum(),
                })
    return pd.DataFrame(rows)


def fragment_summary(fragments, years):
    """Summarize pooled and fold-level opportunity and protection on identical rows."""
    def aggregate(sample):
        return {
            arm: rebound.exposure_tradeoff(rows.original_cash_effect_pp, rows.variant_exposure_vs_dual_pp)
            for arm, rows in sample.groupby("arm", sort=False)
        }

    pooled = aggregate(fragments)
    by_year = {int(year): aggregate(fragments.loc[fragments.year.eq(year)]) for year in years}
    return pooled, by_year
