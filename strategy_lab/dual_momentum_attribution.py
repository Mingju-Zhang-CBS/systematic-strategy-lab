"""Reconciled ETF sleeve attribution for the fixed dual-momentum study."""

import numpy as np
import pandas as pd

from . import dual_momentum as dm

SLEEVES = tuple("/".join(pair) for pair in dm.PAIRS)
CONTROLS = tuple(arm for arm in dm.ARMS if arm != "dual")
EFFECTS = ("cash_off", "active_exposure", "selection", "fees")
PRIMARY_COST = 10


def replay(daily, closes, target, saved, cost_bps=PRIMARY_COST):
    """Recover pre-mark ETF weights and trade dollars using the saved account clock."""
    index = saved.index
    months = index.to_period("M")
    execution = index[~months.duplicated()]
    orders = target.loc[execution.to_period("M") - 1].set_axis(execution)
    quotes = closes.loc[execution, list(dm.ASSETS)]
    if not np.isfinite(quotes).all().all() or (quotes <= 0).any().any():
        raise ValueError("Invalid traded close in attribution replay")

    position = np.r_[np.zeros(8), 1.0]
    risky = np.zeros((len(index), 8))
    fees = np.zeros_like(risky)
    gross_trades = np.zeros_like(risky)
    nav = np.zeros(len(index))
    weights = dict(zip(execution, orders.to_numpy(dtype=float), strict=True))
    returns = daily.loc[index, list(dm.COLUMNS)].to_numpy(dtype=float)
    for i, (date, day_return) in enumerate(zip(index, returns, strict=True)):
        prior_nav = position.sum()
        risky[i] = position[:-1] / prior_nav
        marked = position * (1 + day_return)
        position = marked
        if date in weights:
            position, _, _ = dm.rebalance(marked, weights[date], cost_bps / 10_000)
            traded = np.abs(position[:-1] - marked[:-1])
            fees[i] = (cost_bps / 10_000) * traded / prior_nav
            gross_trades[i] = traded / marked.sum()
        nav[i] = position.sum()
    r = nav / np.r_[1, nav[:-1]] - 1
    if not (
        np.allclose(nav, saved.nav, rtol=1e-12, atol=1e-12)
        and np.allclose(r, saved["return"], rtol=0, atol=1e-12)
        and np.allclose(gross_trades.sum(axis=1), saved.turnover, rtol=0, atol=1e-12)
    ):
        raise ArithmeticError("Attribution replay differs from the frozen ledger")
    return {"r": r, "weights": risky, "fees": fees, "trades": gross_trades, "orders": orders}


def components(dual, control, excess, index):
    """Split daily relative P&L into exposure, ETF mix and fees, then link in logs."""
    left = dual["weights"].reshape(-1, 4, 2)
    right = control["weights"].reshape(-1, 4, 2)
    x = excess.reshape(-1, 4, 2)
    lsize = left.sum(axis=2)
    rsize = right.sum(axis=2)
    lmix = np.divide(left, lsize[..., None], out=np.zeros_like(left), where=lsize[..., None] != 0)
    rmix = np.divide(right, rsize[..., None], out=np.zeros_like(right), where=rsize[..., None] != 0)
    # If one account holds cash, use the other's mix to assign the full gap to exposure.
    lmix = np.where(lsize[..., None] == 0, rmix, lmix)
    rmix = np.where(rsize[..., None] == 0, lmix, rmix)
    lret = (lmix * x).sum(axis=2)
    rret = (rmix * x).sum(axis=2)
    exposure = (lsize - rsize) * (lret + rret) / 2
    selection = (lsize + rsize) * (lret - rret) / 2
    fee_gap = (control["fees"] - dual["fees"]).reshape(-1, 4, 2).sum(axis=2)
    off = (lsize == 0) & (rsize > 0)
    delta = dual["r"] - control["r"]
    log_gap = np.log1p(delta / (1 + control["r"]))
    link = np.divide(log_gap, delta, out=1 / (1 + control["r"]), where=delta != 0)
    values = np.stack(
        [np.where(off, exposure, 0), np.where(off, 0, exposure), selection, fee_gap], axis=2
    ) * link[:, None, None]
    np.testing.assert_allclose(values.sum(axis=(1, 2)), log_gap, rtol=0, atol=2e-12)
    columns = pd.MultiIndex.from_product([SLEEVES, EFFECTS], names=["sleeve", "effect"])
    return pd.DataFrame(values.reshape(-1, 16), index=index, columns=columns), off


def cash_spells(index, dual, relative, linked, off):
    """Rank contiguous cash holds by linked exposure P&L against relative-only."""
    rows = []
    for sleeve, pair in enumerate(dm.PAIRS):
        offset = 2 * sleeve
        positions = np.flatnonzero(off[:, sleeve])
        for spell in np.split(positions, np.flatnonzero(np.diff(positions) != 1) + 1):
            if not len(spell):
                continue
            a, b = spell[0], spell[-1]
            labels = np.asarray(pair)[relative["weights"][spell, offset:offset + 2].argmax(axis=1)]
            path = [labels[0], *labels[1:][labels[1:] != labels[:-1]]]
            # Start is the execution close before the first cash return. End is the
            # next entry close, or the last mark if the sample ends in cash.
            start = index[a - 1]
            end = index[b]
            targets = dual["orders"].loc[:, list(pair)]
            previous = targets.loc[targets.index < start].tail(1)
            sold = ", ".join(previous.columns[previous.iloc[0].gt(0)]) if len(previous) else ""
            bought = ", ".join(targets.columns[targets.loc[end].gt(0)]) if end in targets.index else ""
            rows.append({
                "sleeve": SLEEVES[sleeve], "cash_from_close": start,
                "through_close": end, "sessions": len(spell),
                "sold": sold, "relative_held": " -> ".join(path), "reentry": bought,
                "cash_off_log_pp": 100 * linked[SLEEVES[sleeve], "cash_off"].iloc[spell].sum(),
            })
    return pd.DataFrame(rows).sort_values("cash_off_log_pp", ignore_index=True)


def ranking_events(index, dual, linked):
    """Summarize ETF selection P&L for each active holding interval."""
    rows = []
    orders = dual["orders"].loc[:, list(dm.ASSETS)]
    stops = [*orders.index[1:], index[-1]]
    for (start, target), end in zip(orders.iterrows(), stops, strict=True):
        selected = (index > start) & (index <= end)
        for sleeve, pair in zip(SLEEVES, dm.PAIRS, strict=True):
            if target[list(pair)].max() > 0:
                rows.append({
                    "sleeve": sleeve, "buy_close": start, "through_close": end,
                    "chosen": target[list(pair)].idxmax(),
                    "selection_log_pp": 100 * linked[sleeve, "selection"].loc[selected].sum(),
                })
    return pd.DataFrame(rows).sort_values("selection_log_pp", ignore_index=True)


def turnover_events(index, dual, linked):
    """Label dual ETF orders by the change in monthly sleeve target."""
    rows = []
    orders = dual["orders"].loc[:, list(dm.ASSETS)]
    previous = orders.shift().fillna(0)
    for date, target in orders.iterrows():
        i = index.get_loc(date)
        for sleeve, pair, traded in zip(SLEEVES, dm.PAIRS, dual["trades"][i].reshape(4, 2), strict=True):
            size = traded.sum()
            if size <= 1e-14:
                continue
            before, after = previous.loc[date, list(pair)], target[list(pair)]
            source = before.idxmax() if before.max() > 0 else "cash"
            dest = after.idxmax() if after.max() > 0 else "cash"
            if source == dest:
                kind = "weight reset"
            elif date == orders.index[0]:
                kind = "initial funding"
            elif source == "cash":
                kind = "gate entry"
            elif dest == "cash":
                kind = "gate exit"
            else:
                kind = "winner rotation"
            rows.append({
                "sleeve": sleeve, "trade_close": date, "kind": kind, "from": source,
                "to": dest, "gross_turnover_pct": 100 * size,
                "dual_fee_bps_pretrade_nav": size * PRIMARY_COST,
                "fee_gap_log_pp_vs_relative": 100 * linked.at[date, (sleeve, "fees")],
            })
    return pd.DataFrame(rows)


def attribute(daily, closes, targets, saved):
    """Return full annual/sleeve results and audit event tables."""
    index = saved["dual"].index
    if not all(frame.index.equals(index) for frame in saved.values()):
        raise ValueError("Attribution arms must share the frozen calendar")
    accounts = {arm: replay(daily, closes, targets[arm], saved[arm]) for arm in dm.ARMS}
    dual = accounts["dual"]
    frame = daily.loc[index]
    excess = frame[list(dm.ASSETS)].sub(frame.RF, axis=0).to_numpy(dtype=float)
    output = {}
    comparisons = {}
    for control in CONTROLS:
        linked, off = components(dual, accounts[control], excess, index)
        comparisons[control] = linked
        if control == "relative":
            output["cash_spells"] = cash_spells(index, dual, accounts[control], linked, off)
            output["turnover_events"] = turnover_events(index, dual, linked)
        if control == "same_gate_equal":
            output["ranking_events"] = ranking_events(index, dual, linked)
    combined = pd.concat(comparisons, axis=1, names=["control"])
    annual = combined.groupby(index.year).sum().stack(["control", "sleeve"], future_stack=True)
    output["annual_sleeve"] = (100 * annual).assign(total=lambda x: x.sum(axis=1)).reset_index(names=["year", "control", "sleeve"])
    output["daily_linked"] = combined
    return output
