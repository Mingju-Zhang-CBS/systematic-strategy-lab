"""Evaluate the fixed rebound variants against the frozen WRDS accounts."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr
from strategy_lab import dual_momentum_rebound as rebound
from tools.run_dual_momentum_attribution import load_frozen_inputs

RUN_ID = "dual-momentum-rebound-v1-20261109"


def run(db, rf_path, base_dir):
    returns, closes, monthly, rf, targets = load_frozen_inputs(db, rf_path, base_dir)
    variants = rebound.variant_targets(monthly, targets)
    targets.update(variants)
    output = base_dir / "rebound_v1"
    output.mkdir(exist_ok=True)
    result = {
        "run_id": RUN_ID,
        "variant_sha256": sha256(Path(rebound.__file__).read_bytes()).hexdigest(),
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "metrics": {},
        "paired_10bps": {},
        "subperiod_10bps": {},
    }
    primary = {}
    reconciled = 0
    for cost in dm.COSTS_BPS:
        result["metrics"][cost] = {}
        for arm, weights in targets.items():
            ledger = dm.simulate(returns, closes, weights, cost)
            if arm in dm.ARMS:
                saved = pd.read_csv(base_dir / f"{arm}_{cost}bps_daily.csv", index_col="session", parse_dates=True)
                pd.testing.assert_frame_equal(ledger.rename_axis("session"), saved, rtol=1e-11, atol=1e-12)
                reconciled += 1
            else:
                ledger.to_csv(output / f"{arm}_{cost}bps_daily.csv", index_label="session")
            result["metrics"][cost][arm] = dm.metrics(ledger, rf)
            if cost == attr.PRIMARY_COST:
                primary[arm] = ledger
    months = pd.DataFrame({arm: dm.monthly_marks(ledger["return"]) for arm, ledger in primary.items()})
    for arm in rebound.VARIANTS:
        result["paired_10bps"][arm] = {
            base: dm.paired_log_growth(months[arm], months[base]) for base in dm.ARMS
        }
    for label, sample in {"2012-2019": months.loc[:"2019-12"], "2020-2026H1": months.loc["2020-01":]}.items():
        result["subperiod_10bps"][label] = (12 * np.log1p(sample).mean()).to_dict()
    months.to_csv(output / "monthly_net_10bps.csv", index_label="month")
    annual = (1 + months).groupby(months.index.year).prod() - 1
    annual.to_csv(output / "calendar_year_net_10bps.csv", index_label="year")

    day_index = primary["dual"].index
    window = returns.loc[day_index]
    accounts = {arm: attr.replay(returns, closes, targets[arm], primary[arm]) for arm in ("dual", "relative", *rebound.VARIANTS)}
    excess = window[list(dm.ASSETS)].sub(window.RF, axis=0).to_numpy(dtype=float)
    linked, off = attr.components(accounts["dual"], accounts["relative"], excess, day_index)
    original_spells = attr.cash_spells(day_index, accounts["dual"], accounts["relative"], linked, off)
    spells = rebound.compare_cash_spells(window, accounts, original_spells)
    spells.to_csv(output / "original_cash_spell_comparison_10bps.csv", index=False)
    result["spell_summary_10bps"] = rebound.spell_summary(spells)
    result["original_cash_spells"] = len(original_spells)
    result["reconciled_baseline_ledgers"] = reconciled
    result["months"] = len(months)
    result["sessions"] = len(day_index)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, annual, spells


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True, help="Private directory of frozen WRDS outputs")
    args = parser.parse_args()
    db = wrds.Connection()
    try:
        result, _, _ = run(db, args.rf, args.base_dir)
        print(f"Saved {result['run_id']} with {result['months']} matched evaluation months.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
