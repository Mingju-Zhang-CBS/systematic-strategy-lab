"""Replay fixed and annually selected closed-gate floors on WRDS Cloud."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr
from strategy_lab import dual_momentum_walkforward as wf
from tools.run_dual_momentum_attribution import load_frozen_inputs

RUN_ID = "dual-momentum-floor-walkforward-v1-20261109"
BENCHMARK = "trailing36"


def reconcile(ledger, path):
    archived = pd.read_csv(path, index_col="session", parse_dates=True)
    pd.testing.assert_frame_equal(ledger.rename_axis("session"), archived, rtol=1e-11, atol=1e-12)


def run(db, rf_path, base_dir):
    daily, closes, _, rf, original = load_frozen_inputs(db, rf_path, base_dir)
    fixed = wf.fixed_targets(original)
    portfolios = {**original, **fixed}
    ledgers = {}
    for cost in dm.COSTS_BPS:
        ledgers[cost] = {}
        for arm, weights in portfolios.items():
            ledger = dm.simulate(daily, closes, weights, cost)
            if arm in dm.ARMS:
                reconcile(ledger, base_dir / f"{arm}_{cost}bps_daily.csv")
            if arm == "floor_50":
                reconcile(ledger, base_dir / "rebound_v1" / f"half_risk_{cost}bps_daily.csv")
            ledgers[cost][arm] = ledger

    training = pd.DataFrame({
        arm: dm.monthly_marks(ledgers[attr.PRIMARY_COST][arm]["return"]) for arm in wf.FLOORS
    })
    schedule = wf.folds(training, rf)
    adaptive = wf.selected_targets(fixed, schedule)
    portfolios[wf.ADAPTIVE] = adaptive
    output = base_dir / "floor_walkforward_v1"
    output.mkdir(exist_ok=True)
    result = {
        "run_id": RUN_ID,
        "model_sha256": sha256(Path(wf.__file__).read_bytes()).hexdigest(),
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "metrics": {},
        "test_months": 0,
        "reconciled_ledgers": len(dm.COSTS_BPS) * (len(dm.ARMS) + 1),
        "paired_vs_trailing_10bps": {},
        "fold_wins_vs_trailing": {},
    }
    for cost, books in ledgers.items():
        books[wf.ADAPTIVE] = dm.simulate(daily, closes, adaptive, cost)
        result["metrics"][cost] = {}
        for arm, ledger in books.items():
            test = wf.holdout_ledger(ledger)
            if arm not in dm.ARMS:
                test.to_csv(output / f"{arm}_{cost}bps_holdout.csv", index_label="session")
            result["metrics"][cost][arm] = dm.metrics(test, rf)

    primary = ledgers[attr.PRIMARY_COST]
    months = pd.DataFrame({arm: dm.monthly_marks(wf.holdout_ledger(ledger)["return"]) for arm, ledger in primary.items()})
    expected = pd.period_range(wf.TEST_START, dm.END, freq="M")
    if not months.index.equals(expected):
        raise ArithmeticError("Test months differ from the frozen rolling calendar")
    result["test_months"] = len(months)
    annual = (1 + months).groupby(months.index.year).prod() - 1
    for arm in (*wf.FLOORS, wf.ADAPTIVE):
        result["paired_vs_trailing_10bps"][arm] = dm.paired_log_growth(months[arm], months[BENCHMARK])
        gap = annual[arm] - annual[BENCHMARK]
        result["fold_wins_vs_trailing"][arm] = {
            "wins": int(gap.gt(1e-12).sum()), "ties": int(gap.abs().le(1e-12).sum()), "folds": len(gap)
        }

    arms = ("dual", "relative", *wf.FLOORS, wf.ADAPTIVE)
    accounts = {arm: attr.replay(daily, closes, portfolios[arm], primary[arm]) for arm in arms}
    fragments = wf.cash_spell_fragments(daily.loc[primary["dual"].index], accounts)
    pooled, yearly = wf.fragment_summary(fragments, schedule.index)
    result["spell_pooled_10bps"] = pooled
    result["spell_by_fold_10bps"] = yearly
    original_frags = fragments.loc[fragments.arm.eq("floor_50"), "original_cash_effect_pp"]
    result["fragment_counts"] = {"missed": int(original_frags.lt(0).sum()), "protective": int(original_frags.gt(0).sum())}

    months.to_csv(output / "monthly_net_10bps.csv", index_label="month")
    annual.to_csv(output / "fold_net_10bps.csv", index_label="year")
    fragments.to_csv(output / "cash_spell_fragments_10bps.csv", index=False)
    schedule.to_csv(output / "selection_schedule.csv")
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, schedule, annual, fragments


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True, help="Private WRDS baseline and rebound outputs")
    args = parser.parse_args()
    db = wrds.Connection()
    try:
        result, _, _, _ = run(db, args.rf, args.base_dir)
        print(f"Saved {result['run_id']} with {result['test_months']} holdout months.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
