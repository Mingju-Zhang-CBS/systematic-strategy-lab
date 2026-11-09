"""Calibrate and replay risk-matched CRSP cash-floor accounts on WRDS Cloud."""

import argparse
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

RUN_ID = "dual-momentum-floor-volmatch-v1-20261109"


def load_windows(base_dir):
    windows = pd.read_csv(base_dir / "floor_walkforward_v1" / "selection_schedule.csv", index_col="year")
    windows = windows.loc[:, list(vm.WINDOW_COLUMNS)].apply(lambda column: pd.PeriodIndex(column, freq="M"))
    months = [month for row in windows.itertuples() for month in pd.period_range(row.test_first, row.test_last, freq="M")]
    if not pd.PeriodIndex(months).equals(pd.period_range(wf.TEST_START, dm.END, freq="M")):
        raise ValueError("Archived test folds differ from the original walk-forward calendar")
    return windows


def run(db, rf_path, base_dir):
    daily, closes, _, rf, original = load_frozen_inputs(db, rf_path, base_dir)
    candidates = {"floor_75": wf.fixed_targets(original)["floor_75"], "trailing36": original["trailing36"]}
    windows = load_windows(base_dir)
    schedule = vm.calibrate(daily, closes, candidates, rf, windows)
    targets = {**candidates, **vm.apply_schedule(candidates, schedule)}
    output = base_dir / "floor_volmatch_v1"
    output.mkdir(exist_ok=True)
    result = {
        "run_id": RUN_ID,
        "model_sha256": sha256(Path(vm.__file__).read_bytes()).hexdigest(),
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "metrics": {},
        "paired": {},
        "reconciled": 0,
        "test_months": 0,
    }
    primary = {}
    for cost in dm.COSTS_BPS:
        books = {arm: dm.simulate(daily, closes, weights, cost) for arm, weights in targets.items()}
        reconcile(books["trailing36"], base_dir / f"trailing36_{cost}bps_daily.csv")
        reconcile(
            wf.holdout_ledger(books["floor_75"]),
            base_dir / "floor_walkforward_v1" / f"floor_75_{cost}bps_holdout.csv",
        )
        result["reconciled"] += 2
        result["metrics"][cost] = {}
        months = {}
        for arm, ledger in books.items():
            test = wf.holdout_ledger(ledger)
            months[arm] = dm.monthly_marks(test["return"])
            risk = float(np.sqrt(12) * (months[arm] - rf.reindex(months[arm].index)).std())
            result["metrics"][cost][arm] = {**dm.metrics(test, rf), "annualized_excess_vol": risk}
            if arm in vm.MATCHED:
                test.to_csv(output / f"{arm}_{cost}bps_holdout.csv", index_label="session")
        result["paired"][cost] = {
            "unscaled": dm.paired_log_growth(months["floor_75"], months["trailing36"]),
            "matched": dm.paired_log_growth(months[vm.MATCHED[0]], months[vm.MATCHED[1]]),
        }
        if cost == attr.PRIMARY_COST:
            primary = books
            result["test_months"] = len(months[vm.MATCHED[0]])
            pd.DataFrame(months).to_csv(output / "monthly_net_10bps.csv", index_label="month")

    for arm in ("relative", "dual"):
        primary[arm] = dm.simulate(daily, closes, original[arm], attr.PRIMARY_COST)
        reconcile(primary[arm], base_dir / f"{arm}_{attr.PRIMARY_COST}bps_daily.csv")
        result["reconciled"] += 1

    folds = {}
    for year, row in schedule.iterrows():
        folds[int(year)] = {
            arm: vm.period_risk(ledger, rf, row.test_first, row.test_last)
            for arm, ledger in primary.items()
        }
    result["folds_10bps"] = folds
    wins = sum(row[vm.MATCHED[0]]["net"] > row[vm.MATCHED[1]]["net"] + 1e-12 for row in folds.values())
    ties = sum(abs(row[vm.MATCHED[0]]["net"] - row[vm.MATCHED[1]]["net"]) <= 1e-12 for row in folds.values())
    result["matched_fold_wins"] = {"wins": wins, "ties": ties, "folds": len(folds)}

    arms = ("dual", "relative", *targets)
    accounts = {
        arm: attr.replay(daily, closes, targets[arm] if arm in targets else original[arm], primary[arm])
        for arm in arms
    }
    fragments = wf.cash_spell_fragments(daily.loc[primary["dual"].index], accounts, compared=tuple(targets))
    _, detail = wf.fragment_summary(fragments, [2022])
    result["protection_2022"] = detail[2022]
    result["max_training_vol_gap"] = float((schedule[f"{vm.BASES[0]}_fitted_vol"] - schedule[f"{vm.BASES[1]}_fitted_vol"]).abs().max())
    if result["max_training_vol_gap"] > vm.VOL_TOL:
        raise ArithmeticError("Volatility match failed")
    schedule.to_csv(output / "volatility_schedule.csv")
    fragments.to_csv(output / "cash_spell_fragments_10bps.csv", index=False)
    pd.DataFrame.from_records([
        {"fold": year, "arm": arm, **row} for year, values in folds.items() for arm, row in values.items()
    ]).to_csv(output / "fold_risk_10bps.csv", index=False)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, schedule


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True, help="Private baseline and walk-forward outputs")
    args = parser.parse_args()
    db = wrds.Connection()
    try:
        result, _ = run(db, args.rf, args.base_dir)
        print(f"Saved {result['run_id']} with {result['test_months']} matched test months.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
