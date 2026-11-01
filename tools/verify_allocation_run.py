"""Independent vectorized trade/units/cash reconstruction; no allocation imports."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def actual_file(path):
    return path if path.exists() else Path(str(path)+".gz")


def read_csv(path):return pd.read_csv(actual_file(path),float_precision="round_trip")


def audit(path):
    root=Path(path);manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    for name,digest in manifest["artifacts"].items():
        target=(root/name).resolve()
        assert target.is_relative_to(root.resolve()) and target.is_file(),name
        assert hashlib.sha256(target.read_bytes()).hexdigest()==digest,name
    for name,record in manifest.get("snapshot",{}).get("compressed_artifacts",{}).items():
        original=gzip.decompress((root/name).read_bytes())
        assert hashlib.sha256(original).hexdigest()==record["uncompressed_sha256"],name
    protocol=json.loads((root/"protocol.json").read_text());cfg=protocol["config"];assets=protocol["assets"]
    metrics=read_csv(root/"metrics.csv");intervals=read_csv(root/"paired_inference.csv")
    assert len(metrics)==552 and len(intervals)==144
    events=read_csv(root/"optimization_events.csv")
    assert (events.train_end<=events.decision_date).all()
    good=events[events.status.eq("ok")]
    assert (good.optimality_residual<=cfg["optimality_tolerance"]).all()
    fractions=good[["risk_fraction_"+a for a in assets]].to_numpy()
    assert np.max(np.abs(fractions.sum(axis=1)-1))<1e-10
    count=0;largest=0.;common=None
    for bps in protocol["cost_bps"]:
        for rate in protocol["continuous_cash_rates"]:
            directory=root/f"cost-{bps:02d}_cash-{int(rate*100):02d}"
            for variant in [v["name"] for v in protocol["variants"]]:
                path=actual_file(directory/f"{variant}_ledger.csv")
                if not path.exists() and "snapshot" in manifest:continue
                ledger=read_csv(path);trades=read_csv(directory/f"{variant}_trades.csv")
                decisions=read_csv(directory/f"{variant}_decisions.csv")
                dates=pd.DatetimeIndex(pd.to_datetime(ledger.date));date_strings=ledger.date.tolist()
                if common is None:common=date_strings
                assert date_strings==common and not dates.has_duplicates and dates.is_monotonic_increasing
                positions={date:i for i,date in enumerate(date_strings)}
                scheduled=decisions[decisions.status.eq("scheduled")]
                for row in scheduled.itertuples():
                    assert positions[row.execution_date]==positions[row.decision_date]+1
                if len(trades):
                    assert np.max(np.abs(trades.quantity*trades.model_unit_price-trades.signed_notional))<1e-7
                    assert np.max(np.abs(trades.signed_notional.abs()*bps/10000-trades.fee))<1e-8
                def trade_table(column):
                    if trades.empty:return np.zeros((len(dates),len(assets)))
                    table=trades.pivot_table(index="execution_date",columns="ticker",values=column,aggfunc="sum")
                    return table.reindex(index=date_strings,columns=assets).fillna(0.).to_numpy()
                signed=trade_table("signed_notional");fee=trade_table("fee").sum(axis=1)
                units=np.cumsum(trade_table("quantity"),axis=0)
                prices=ledger[["price_"+a for a in assets]].to_numpy()
                days=np.r_[0.,np.diff(dates.asi8)/86400e9]
                growth=np.exp(rate*np.cumsum(days)/365.25)
                cash=growth*(cfg["initial_nav"]-np.cumsum((signed.sum(axis=1)+fee)/growth))
                nav=cash+(units*prices).sum(axis=1)
                previous_units=np.vstack([np.zeros(len(assets)),units[:-1]])
                previous_prices=np.vstack([prices[0],prices[:-1]])
                previous_nav=np.r_[cfg["initial_nav"],nav[:-1]]
                previous_cash=np.r_[cfg["initial_nav"],cash[:-1]]
                interest=previous_cash*np.expm1(rate*days/365.25)
                pnl=(previous_units*(prices-previous_prices)).sum(axis=1)
                residual=max(float(np.max(np.abs(nav-ledger.nav))),float(np.max(np.abs(cash-ledger.cash))),
                             float(np.max(np.abs(units-ledger[["units_"+a for a in assets]].to_numpy())*prices)),
                             float(np.max(np.abs(interest-ledger.cash_interest))),float(np.max(np.abs(pnl-ledger.security_pnl))),
                             float(np.max(np.abs(fee-ledger.fee))))
                largest=max(largest,residual);assert residual<2e-6,(variant,bps,rate,residual)
                assert (ledger.cash>=0).all() and (ledger.held_exposure<=1+1e-9).all()
                gross=np.abs(signed).sum(axis=1)
                assert np.max(np.abs(gross/(previous_nav+pnl+interest)-ledger.turnover))<1e-10
                for row in scheduled.itertuples():
                    i=positions[row.execution_date]
                    observed=units[i]*prices[i]/nav[i]
                    requested=np.array([getattr(row,"target_"+a) for a in assets])
                    assert requested.min()>=0 and requested.max()<=cfg["weight_cap"]+1e-8
                    np.testing.assert_allclose(observed,requested,atol=2e-10,rtol=0)
                count+=1
    if "snapshot" not in manifest:assert count==138
    return {"data_kind":manifest["data_kind"],"artifact_hashes_checked":len(manifest["artifacts"]),
            "accounts_reconstructed":count,"maximum_account_residual":largest,"metrics_rows":len(metrics),"paired_rows":len(intervals)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path)
    parser.add_argument("--receipt",type=Path);args=parser.parse_args();result=audit(args.run)
    text=json.dumps(result,indent=2);print(text)
    if args.receipt:args.receipt.write_text(text+"\n",encoding="utf-8")


if __name__=="__main__":main()
