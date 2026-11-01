"""Independent artifact and trade-cash-flow audit; no import of the account engine."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

METHODS = ("buy_hold", "vol_hold", "raw_momentum", "ema_momentum", "kalman_momentum", "kalman_hmm")


def audit(path):
    root = Path(path)
    manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifacts"].items():
        file = (root/name).resolve()
        if not file.is_relative_to(root.resolve()) or not file.is_file():
            raise AssertionError(f"Missing or unsafe artifact {name}")
        assert hashlib.sha256(file.read_bytes()).hexdigest() == expected, name
    cfg = json.loads((root/"protocol.json").read_text())["config"]
    summary = pd.read_csv(root/"metrics.csv",float_precision="round_trip")
    assert len(summary) == 288
    inference = pd.read_csv(root/"paired_inference.csv",float_precision="round_trip")
    assert len(inference) == 96
    largest = 0.; accounts = 0
    for asset in ("SPY", "QQQ"):
        states = pd.read_csv(root/asset/"state_probabilities.csv",float_precision="round_trip")
        good = states.status.eq("ok")
        probabilities = states.loc[good,["p_0","p_1","p_2"]].to_numpy()
        assert np.isfinite(probabilities).all() and (probabilities >= 0).all() and (probabilities <= 1).all()
        assert np.max(np.abs(probabilities.sum(axis=1)-1)) < 1e-12
        fits = pd.read_csv(root/asset/"training_events.csv")
        assert (fits.train_end < fits.decision_date).all()
        common = None
        for bps in (0,5,10):
            for rate in (0.,.03):
                case = root/asset/f"cost-{bps:02d}_cash-{int(rate*100):02d}"
                for method in METHODS:
                    ledger_path = case/f"{method}_ledger.csv"
                    if not ledger_path.exists() and "snapshot" in manifest:
                        continue
                    ledger = pd.read_csv(ledger_path,float_precision="round_trip").fillna({"executed_decision_date":""})
                    trades = pd.read_csv(case/f"{method}_trades.csv",float_precision="round_trip")
                    decisions = pd.read_csv(case/f"{method}_decisions.csv",float_precision="round_trip")
                    if common is None: common = ledger.date.tolist()
                    assert ledger.date.tolist() == common
                    assert common == states.date.tolist()
                    assert len(set(common)) == len(common)
                    date_positions = {date:i for i,date in enumerate(common)}
                    for r in decisions.itertuples():
                        if r.status == "scheduled":
                            assert date_positions[r.execution_date] == date_positions[r.decision_date]+1
                    by_day = {date:frame for date,frame in trades.groupby("execution_date")}
                    cash = cfg["initial_nav"]; units = 0.; previous_date = pd.Timestamp(common[0])
                    previous_price = float(ledger.model_unit_price.iloc[0]); previous_nav = cash
                    for row in ledger.itertuples():
                        date = pd.Timestamp(row.date)
                        interest = cash*np.expm1(rate*(date-previous_date).days/365.25)
                        pnl = units*(row.model_unit_price-previous_price)
                        cash += interest
                        held = units*previous_price/previous_nav
                        today = by_day.get(row.date)
                        gross = fees = 0.
                        if today is not None:
                            for trade in today.itertuples():
                                assert date_positions[trade.execution_date] == date_positions[trade.decision_date]+1
                                signed = trade.quantity*trade.model_unit_price
                                fee = abs(signed)*bps/10000
                                assert abs(signed-trade.signed_notional) < 1e-7
                                assert abs(fee-trade.fee) < 1e-8
                                cash -= signed+fee; units += trade.quantity
                                gross += abs(signed); fees += fee
                        nav = cash+units*row.model_unit_price
                        residual = max(abs(nav-row.nav),abs(cash-row.cash),
                                       abs(units-row.units)*row.model_unit_price,
                                       abs(interest-row.cash_interest),abs(pnl-row.security_pnl),
                                       abs(held-row.held_weight)*previous_nav,abs(fees-row.fee))
                        largest = max(largest,residual)
                        assert residual < 1e-6, (asset,method,row.date,residual)
                        assert row.cash >= 0 and -1e-12 <= row.end_weight <= 1+1e-12
                        assert abs(row.turnover-gross/(previous_nav+pnl+interest)) < 1e-10
                        previous_price=row.model_unit_price;previous_date=date;previous_nav=nav
                    accounts += 1
    if "snapshot" not in manifest:
        assert accounts == 72
    return {"data_kind":manifest["data_kind"], "artifacts_checked":len(manifest["artifacts"]),
            "accounts_reconstructed":accounts,"maximum_account_residual":largest,
            "metrics_rows":len(summary),"paired_rows":len(inference)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    print(json.dumps(audit(args.run),indent=2))


if __name__ == "__main__":main()
