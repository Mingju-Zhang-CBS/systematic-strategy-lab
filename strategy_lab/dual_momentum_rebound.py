"""Fixed cash-floor and earlier re-entry variants of the dual-momentum gate."""

import numpy as np
import pandas as pd

from . import dual_momentum as dm
from . import dual_momentum_attribution as attr

VARIANTS = ("half_risk", "reentry_3m")


def variant_targets(monthly, original):
    """Keep ranking and clock fixed, altering only the gate's risky sleeve weight."""
    relative = original["relative"]
    dual = original["dual"]
    half = 0.5 * (relative + dual)
    reentry = dual.copy()
    trailing3 = ((1 + monthly).rolling(3).apply(np.prod, raw=True) - 1).loc[dual.index]

    for pair in dm.PAIRS:
        columns = list(pair)
        winners = relative[columns]
        gate_open = dual[columns].sum(axis=1).gt(0)
        winner3 = trailing3[columns].where(winners.gt(0)).sum(axis=1, min_count=1)
        # The first closed decision still exits. The three-month hurdle only
        # acts during an already closed spell, using the current monthly winner.
        faster = ~gate_open.shift(1, fill_value=True) & winner3.gt(trailing3.RF)
        reentry[columns] = winners.mul(gate_open | faster, axis=0)
    reentry["RF"] = 1 - reentry[list(dm.ASSETS)].sum(axis=1)
    return dict(zip(VARIANTS, [half, reentry], strict=True))


def compare_cash_spells(daily, accounts, original_spells):
    """Measure each variant's linked exposure on the same original cash spells."""
    index = daily.index
    excess = daily[list(dm.ASSETS)].sub(daily.RF, axis=0).to_numpy(dtype=float)
    frames = []
    for arm in VARIANTS:
        linked, _ = attr.components(accounts[arm], accounts["dual"], excess, index)
        rows = []
        for spell in original_spells.itertuples(index=False):
            affected = (index > spell.cash_from_close) & (index <= spell.through_close)
            effect = linked.loc[affected, (spell.sleeve, "active_exposure")]
            orders = accounts[arm]["orders"]
            span = orders.loc[
                (orders.index >= spell.cash_from_close) & (orders.index < spell.through_close),
                spell.sleeve.split("/"),
            ]
            invested = span.index[span.sum(axis=1).gt(0)]
            rows.append({
                "arm": arm,
                "sleeve": spell.sleeve,
                "original_cash_from": spell.cash_from_close,
                "original_cash_through": spell.through_close,
                "original_relative_held": spell.relative_held,
                "original_cash_effect_pp": spell.cash_off_log_pp,
                "first_variant_risk_close": invested[0] if len(invested) else pd.NaT,
                "variant_exposure_vs_dual_pp": 100 * effect.sum(),
            })
        frames.append(pd.DataFrame(rows))
    return pd.concat(frames, ignore_index=True)


def exposure_tradeoff(original, delta):
    """Aggregate linked exposure over positive and negative baseline windows."""
    miss = original.lt(0)
    save = original.gt(0)
    missed = -original[miss].sum()
    saved = original[save].sum()
    recovered = delta[miss].sum()
    surrendered = -delta[save].sum()
    return {
        "baseline_missed_pp": float(missed),
        "baseline_saved_pp": float(saved),
        "recovered_pp": float(recovered),
        "surrendered_pp": float(surrendered),
        "miss_capture_fraction": float(recovered / missed) if missed else None,
        "protection_retained_fraction": float(1 - surrendered / saved) if saved else None,
    }


def spell_summary(spells):
    rows = {}
    for arm, sample in spells.groupby("arm", sort=False):
        original = sample.original_cash_effect_pp
        rows[arm] = {
            **exposure_tradeoff(original, sample.variant_exposure_vs_dual_pp),
            "touched_missed_spells": int(sample.loc[original.lt(0), "first_variant_risk_close"].notna().sum()),
            "touched_protective_spells": int(sample.loc[original.gt(0), "first_variant_risk_close"].notna().sum()),
        }
    return rows
