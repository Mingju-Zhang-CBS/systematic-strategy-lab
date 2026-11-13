"""Attribute the frozen 12-month risk floor to sleeves, years and execution intervals."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr
from strategy_lab import dual_momentum_volmatch as vm
from strategy_lab import dual_momentum_walkforward as wf
from tools.run_dual_momentum_attribution import load_frozen_inputs
from tools.run_dual_momentum_walkforward import reconcile

RUN_ID = "dual-momentum-12m-attribution-v1-20261113"


def run(db, rf_path, base_dir):
    daily, closes, _, _, original = load_frozen_inputs(db, rf_path, base_dir)
    floor = wf.fixed_targets(original)["floor_75"]
    candidates = {"floor_75": floor, "trailing36": original["trailing36"]}
    targets = {"trailing_original": original["trailing36"], "relative": original["relative"], "dual": original["dual"]}
    locations = {
        "floor_12": base_dir / "floor_monthly_volmatch_12m_v1" / "floor_75_matched_10bps_holdout.csv",
        "trailing_12": base_dir / "floor_monthly_volmatch_12m_v1" / "trailing36_matched_10bps_holdout.csv",
        "floor_60": base_dir / "floor_monthly_volmatch_v1" / "floor_75_matched_10bps_holdout.csv",
    }
    schedules = {}
    for months in (12, 60):
        folder = "floor_monthly_volmatch_v1" if months == 60 else "floor_monthly_volmatch_12m_v1"
        schedule = pd.read_csv(base_dir / folder / "volatility_schedule.csv", index_col="test_month")
        for column in vm.WINDOW_COLUMNS:
            schedule[column] = pd.PeriodIndex(schedule[column], freq="M")
        schedules[months] = schedule
        matched = vm.apply_schedule(candidates, schedule)
        targets[f"floor_{months}"] = matched["floor_75_matched"]
        if months == 12:
            targets["trailing_12"] = matched["trailing36_matched"]

    accounts = {}
    books = {}
    for arm, weights in targets.items():
        ledger = dm.simulate(daily, closes, weights, attr.PRIMARY_COST)
        if arm in locations:
            reconcile(wf.holdout_ledger(ledger), locations[arm])
        else:
            source = "trailing36" if arm == "trailing_original" else arm
            reconcile(ledger, base_dir / f"{source}_10bps_daily.csv")
        accounts[arm] = attr.replay(daily, closes, weights, ledger)
        books[arm] = ledger

    full_index = books["floor_12"].index
    test_mask = full_index.to_period("M") >= pd.Period(wf.TEST_START, "M")
    index = full_index[test_mask]
    excess = daily.loc[full_index, list(dm.ASSETS)].sub(daily.loc[full_index, "RF"], axis=0).to_numpy(dtype=float)
    comparisons = {}
    for arm in ("floor_60", "trailing_original", "trailing_12", "relative", "dual"):
        linked, _ = attr.components(accounts["floor_12"], accounts[arm], excess, full_index)
        comparisons[arm] = linked.loc[index]
    combined = pd.concat(comparisons, axis=1, names=["control"])
    annual = combined.groupby(index.year).sum().stack(["control", "sleeve"], future_stack=True)
    annual = (100 * annual).assign(total=lambda row: row.sum(axis=1)).reset_index(names=["year", "control", "sleeve"])

    # Execution-interval attribution includes the old positions through the next
    # execution close. A calendar year can split one such interval.
    execution_dates = accounts["floor_12"]["orders"].index
    execution_dates = execution_dates[execution_dates >= index[0]]
    interval_ends = [*execution_dates[1:], index[-1]]
    records = []
    for control in ("floor_60", "trailing_original", "trailing_12"):
        linked = comparisons[control]
        left_orders, right_orders = accounts["floor_12"]["orders"], accounts[control]["orders"]
        for start, end in zip(execution_dates, interval_ends, strict=True):
            included = (index > start) & (index <= end)
            test_month = start.to_period("M")
            signal = test_month - 1
            for j, (sleeve, pair) in enumerate(zip(attr.SLEEVES, dm.PAIRS, strict=True)):
                columns = list(pair)
                before = targets["floor_12"].loc[signal - 1, columns].sum()
                now = left_orders.loc[start, columns].sum()
                other = right_orders.loc[start, columns].sum()
                changes = {
                    "previous_floor_target_pct": float(100 * before),
                    "floor_target_pct": float(100 * now),
                    "control_target_pct": float(100 * other),
                    "floor_target_change_pp": float(100 * (now - before)),
                    "floor_scale": float(schedules[12].loc[str(test_month), "floor_75_scale"]),
                    "scale_change_pp": float(100 * (
                        schedules[12].loc[str(test_month), "floor_75_scale"]
                        - (schedules[12].loc[str(test_month - 1), "floor_75_scale"] if str(test_month - 1) in schedules[12].index else 1.0)
                    )),
                    "dual_gate_open": bool(original["dual"].loc[signal, columns].sum() > 0),
                }
                effect = 100 * linked[sleeve].loc[included].sum()
                fee_at_execution = 100 * linked.at[start, (sleeve, "fees")]
                source_i = full_index.get_loc(start)
                direct_trade = accounts["floor_12"]["trades"][source_i, 2*j:2*j + 2].sum()
                records.append({
                    "control": control, "sleeve": sleeve, "execution_close": start,
                    "through_close": end, "winner": floor.loc[signal, columns].idxmax(),
                    **changes,
                    "exposure_log_pp": float(effect["cash_off"] + effect["active_exposure"]),
                    "selection_log_pp": float(effect["selection"]),
                    "fee_log_pp_during_hold": float(effect["fees"]),
                    "total_log_pp_during_hold": float(effect.sum()),
                    "fee_gap_at_entry_log_pp": float(fee_at_execution),
                    "floor_trade_pct_nav": float(100 * direct_trade),
                })
    intervals = pd.DataFrame(records)
    opening_carry = 100 * combined.iloc[:1]
    for control in ("floor_60", "trailing_original", "trailing_12"):
        accounted = intervals.loc[intervals.control.eq(control), "total_log_pp_during_hold"].sum()
        accounted += opening_carry[control].to_numpy().sum()
        np.testing.assert_allclose(accounted, 100 * comparisons[control].to_numpy().sum(), rtol=0, atol=1e-9)

    # Split 2022 contributions by the original gate state that actually earned
    # that day's return, using pre-mark positions from the reconciled account.
    earned_gate = accounts["dual"]["weights"].reshape(-1, 4, 2).sum(axis=2)[test_mask] > 0
    protection = []
    in_2022 = index.year == 2022
    for control in ("relative", "floor_60", "trailing_original", "trailing_12", "dual"):
        linked = comparisons[control]
        for j, sleeve in enumerate(attr.SLEEVES):
            for opened, label in ((True, "original_gate_open"), (False, "original_gate_closed")):
                mask = in_2022 & (earned_gate[:, j] == opened)
                row = 100 * linked[sleeve].loc[mask].sum()
                protection.append({"control": control, "sleeve": sleeve, "gate": label,
                                   **row.to_dict(), "total": float(row.sum())})
    protection = pd.DataFrame(protection)

    # Confirm yearly effect sums independently against the frozen account returns.
    errors = []
    for control in comparisons:
        for year in range(2017, 2027):
            lhs = annual.loc[annual.control.eq(control) & annual.year.eq(year), "total"].sum()
            left = books["floor_12"].loc[str(year), "return"]
            right = books[control].loc[str(year), "return"]
            expected = 100 * (np.log1p(left).sum() - np.log1p(right).sum())
            errors.append(abs(lhs - expected))
    np.testing.assert_allclose(errors, 0, rtol=0, atol=1e-9)

    output = base_dir / "floor_12m_attribution_v1"
    output.mkdir(exist_ok=True)
    annual.to_csv(output / "annual_sleeve.csv", index=False)
    intervals.to_csv(output / "execution_intervals.csv", index=False)
    protection.to_csv(output / "protection_2022.csv", index=False)
    combined.to_csv(output / "daily_linked.csv")
    opening_carry.to_csv(output / "opening_test_mark.csv")
    summary = {
        "run_id": RUN_ID,
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "reconciled_accounts": len(accounts),
        "test_sessions": len(index),
        "annual_rows": len(annual),
        "interval_rows": len(intervals),
        "max_annual_log_reconciliation_pp": max(errors),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary, annual, intervals, protection


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    args = parser.parse_args()
    with closing(wrds.Connection()) as db:
        summary, _, _, _ = run(db, args.rf, args.base_dir)
    print(f"Saved {summary['run_id']} to the private result directory.")


if __name__ == "__main__":
    main()
