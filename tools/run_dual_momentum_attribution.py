"""Attribute the frozen CRSP dual-momentum run within an authorized WRDS environment."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from strategy_lab import dual_momentum as dm
from strategy_lab import dual_momentum_attribution as attr
from tools import run_dual_momentum_wrds as baseline


def run(db, rf_path, base_dir):
    summary = json.loads((base_dir / "summary.json").read_text(encoding="utf-8"))
    if summary["run_id"] != baseline.RUN_ID:
        raise ValueError("Unexpected baseline run")
    fingerprints = {
        "model_sha256": sha256(Path(dm.__file__).read_bytes()).hexdigest(),
        "rf_sha256": sha256(rf_path.read_bytes()).hexdigest(),
    }
    ids, daily, monthly, _, calendar = baseline.query(db)
    fingerprints["crsp_daily_fingerprint"] = sha256(
        pd.util.hash_pandas_object(daily, index=False).to_numpy().tobytes()
    ).hexdigest()
    if any(summary[key] != value for key, value in fingerprints.items()):
        raise ValueError("Inputs differ from the frozen baseline")
    etf, closes, formation, _ = baseline.validate(ids, daily, monthly, calendar)
    rf = pd.read_csv(rf_path, index_col="month")["RF"]
    rf.index = pd.PeriodIndex(rf.index, freq="M")
    returns = dm.session_returns(etf, rf)
    targets = dm.target_weights(formation.assign(RF=rf))
    saved = {
        arm: pd.read_csv(
            base_dir / f"{arm}_{attr.PRIMARY_COST}bps_daily.csv", index_col="session", parse_dates=True
        )
        for arm in dm.ARMS
    }
    outputs = attr.attribute(returns, closes, targets, saved)
    destination = base_dir / "attribution"
    destination.mkdir(exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(destination / f"{name}.csv", index=name == "daily_linked")
    return outputs


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True, help="Private directory of frozen WRDS outputs")
    args = parser.parse_args()
    db = wrds.Connection()
    try:
        outputs = run(db, args.rf, args.base_dir)
        print(f"Saved {len(outputs['annual_sleeve'])} reconciled year/arm/sleeve rows to the private directory.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
