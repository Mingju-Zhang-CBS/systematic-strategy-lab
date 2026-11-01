"""Independently reconstruct funded accounts from trades; no strategy imports."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def actual(path):return path if path.exists() else Path(str(path)+".gz")


def read(path):return pd.read_csv(actual(path),float_precision="round_trip")


def audit(path):
    root=Path(path);manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    for name,digest in manifest["artifacts"].items():
        target=(root/name).resolve();assert target.is_relative_to(root.resolve()) and target.is_file(),name
        assert hashlib.sha256(target.read_bytes()).hexdigest()==digest,name
    for name,item in manifest.get("snapshot",{}).get("compressed_artifacts",{}).items():
        assert hashlib.sha256(gzip.decompress((root/name).read_bytes())).hexdigest()==item["uncompressed_sha256"],name
    p=json.loads((root/"protocol.json").read_text());cfg=p["hmm_config"]
    summary=read(root/"metrics.csv");paired=read(root/"paired_inference.csv")
    assert len(summary)==864 and len(paired)==480
    assert not summary.duplicated(["asset","segment","strategy","cost_bps","cash_rate"]).any()
    assert summary.groupby(["asset","segment"]).observations.nunique().eq(1).all()
    count=0;largest=0.
    for asset in p["assets"]:
        states=read(root/asset/"state_probabilities.csv");fits=read(root/asset/"training_events.csv")
        good=states[states.status.eq("ok")][["p_0","p_1","p_2"]].to_numpy()
        assert len(good) and np.isfinite(good).all() and (good>=0).all() and (good<=1).all()
        assert np.max(np.abs(good.sum(axis=1)-1))<1e-12 and (fits.train_end<fits.decision_date).all()
        common=states.date.tolist()
        for bps in p["cost_bps"]:
            for rate in p["continuous_cash_rates"]:
                folder=root/asset/f"cost-{bps:02d}_cash-{int(rate*100):02d}"
                retained={}
                for strategy in p["strategies"]:
                    if not actual(folder/f"{strategy}_ledger.csv").exists() and "snapshot" in manifest:continue
                    l=read(folder/f"{strategy}_ledger.csv");t=read(folder/f"{strategy}_trades.csv");d=read(folder/f"{strategy}_decisions.csv")
                    assert l.date.tolist()==common and len(set(common))==len(common)
                    positions={date:i for i,date in enumerate(common)};dates=pd.DatetimeIndex(pd.to_datetime(common))
                    scheduled=d[d.status.eq("scheduled")]
                    for row in scheduled.itertuples():assert positions[row.execution_date]==positions[row.decision_date]+1
                    if len(t):
                        assert np.max(np.abs(t.quantity*t.model_unit_price-t.signed_notional))<1e-7
                        assert np.max(np.abs(t.signed_notional.abs()*bps/10000-t.fee))<1e-8
                        joined=t.merge(scheduled,on=["decision_date","execution_date"],suffixes=("_trade","_request"),validate="one_to_one")
                        assert len(joined)==len(t)
                        np.testing.assert_allclose(joined.target_weight_trade,joined.target_weight_request,atol=0,rtol=0)
                    table=t.groupby("execution_date")[["quantity","signed_notional","fee"]].sum().reindex(common).fillna(0.)
                    units=table.quantity.cumsum().to_numpy();signed=table.signed_notional.to_numpy();fee=table.fee.to_numpy()
                    days=np.r_[0.,np.diff(dates.asi8)/86400e9];growth=np.exp(rate*np.cumsum(days)/365.25)
                    cash=growth*(cfg["initial_nav"]-np.cumsum((signed+fee)/growth))
                    prices=l.model_unit_price.to_numpy();nav=cash+units*prices
                    pu=np.r_[0.,units[:-1]];pp=np.r_[prices[0],prices[:-1]];pn=np.r_[cfg["initial_nav"],nav[:-1]]
                    pc=np.r_[cfg["initial_nav"],cash[:-1]];interest=pc*np.expm1(rate*days/365.25);pnl=pu*(prices-pp)
                    residual=max(float(np.max(np.abs(a-b))) for a,b in [(nav,l.nav),(cash,l.cash),(units*prices,l.units*prices),
                                 (interest,l.cash_interest),(pnl,l.security_pnl),(fee,l.fee)])
                    largest=max(largest,residual);assert residual<2e-6,(asset,strategy,bps,rate,residual)
                    assert (l.cash>=0).all() and (l.end_weight.between(0,1+1e-12)).all()
                    np.testing.assert_allclose(pu*pp/pn,l.held_weight,atol=2e-10,rtol=0)
                    np.testing.assert_allclose(np.abs(signed)/(pn+pnl+interest),l.turnover,atol=1e-10,rtol=0)
                    np.testing.assert_allclose(nav/pn-1,l["return"],atol=1e-11,rtol=0)
                    indices=[positions[x] for x in scheduled.execution_date]
                    np.testing.assert_allclose(units[indices]*prices[indices]/nav[indices],scheduled.target_weight,atol=2e-10,rtol=0)
                    assert l.units.iloc[0]==0 and l.fee.iloc[0]==0
                    if strategy!="buy_hold":assert d.status.iloc[-1]=="not_executed_end_of_snapshot"
                    retained[strategy]=l;count+=1
                factor={k:retained.get("channel55__"+k) for k in ["breakout","vol_breakout","hmm_breakout","hmm_vol_breakout"]}
                if all(x is not None for x in factor.values()):
                    contrasts=[("hmm_vol_breakout","vol_breakout"),("vol_breakout","breakout"),("hmm_breakout","breakout"),("hmm_vol_breakout","hmm_breakout")]
                    diffs={a+" minus "+b:factor[a]["return"]-factor[b]["return"] for a,b in contrasts}
                    diffs["interaction"]=diffs["hmm_vol_breakout minus vol_breakout"]-diffs["hmm_breakout minus breakout"]
                    for label,diff in diffs.items():
                        for segment,(lo,hi) in p["segments"].items():
                            mask=factor["breakout"].date.between(lo,hi)
                            values=paired[(paired.asset==asset)&(paired.segment==segment)&(paired.cost_bps==bps)&(paired.cash_rate==rate)&(paired.comparison==label)]
                            assert len(values)==2
                            np.testing.assert_allclose(values.annualized_mean_difference,diff[mask].mean()*252,atol=1e-12,rtol=0)
    assert count==(12 if "snapshot" in manifest else 216)
    return {"status":"PASS","data_kind":manifest["data_kind"],"artifact_hashes_checked":len(manifest["artifacts"]),
            "accounts_reconstructed":count,"maximum_account_residual":largest,"metrics_rows":len(summary),"paired_rows":len(paired)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path);parser.add_argument("--receipt",type=Path)
    args=parser.parse_args();result=audit(args.run);value=json.dumps(result,indent=2);print(value)
    if args.receipt:args.receipt.write_text(value+"\n",encoding="utf-8")


if __name__=="__main__":main()
