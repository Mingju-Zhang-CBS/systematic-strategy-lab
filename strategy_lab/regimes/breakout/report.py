"""Fixed factorial experiment; all periods, costs and sensitivities survive reporting."""
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from ..config import RegimeConfig,SEGMENTS
from ..engine import metrics,paired_interval
from ...runtime import require_empty_output
from .config import ASSETS,FACTORS,COMPARISONS,BreakoutConfig,names,protocol
from .data import validate_bars
from .reference import sha256,closes_hash,load_parent,compare_states,compare_control
from .research import prepare_asset,run_account


def write_json(path,value):
    Path(path).write_bytes((json.dumps(value,indent=2,allow_nan=False)+"\n").encode())


def write_csv(path,frame):frame.to_csv(path,index=False,float_format="%.17g",lineterminator="\n")


def primary_contrasts(ledgers):
    x={key:ledgers["channel55__"+key] for key in FACTORS}
    for a,b in COMPARISONS:
        yield a+" minus "+b,x[a]["return"]-x[b]["return"],x[a].held_weight-x[b].held_weight
    yield "interaction",(x["hmm_vol_breakout"]["return"]-x["vol_breakout"]["return"]
                        -x["hmm_breakout"]["return"]+x["breakout"]["return"]),(
        x["hmm_vol_breakout"].held_weight-x["vol_breakout"].held_weight
        -x["hmm_breakout"].held_weight+x["breakout"].held_weight)


def run_study(bars,output,cfg=BreakoutConfig(),data_kind="synthetic",source=None,parent=None):
    cfg.validate();d=validate_bars(bars)
    if data_kind not in {"synthetic","private-real-current-vintage"}:raise ValueError("Known evidence type required")
    bound=load_parent(parent,data_kind,source,closes_hash(d)) if parent else None
    if data_kind!="synthetic" and not bound:raise ValueError("Real transfer requires bound parent run")
    out=require_empty_output(output);write_json(out/"protocol.json",protocol(cfg))
    rows=[];intervals=[];diagnostics=[];proof={"parent_bound":bool(bound),"states":[],"controls":[]}
    if bound:proof["parent_manifest_sha256"]=sha256(bound[0]/"manifest.json")
    base={}
    for asset in ASSETS:
        print(f"{data_kind}: frozen HMM and breakout {asset}",flush=True)
        b=d[d.ticker.eq(asset)].set_index("date")
        f,states,fits,snapshots,weights,signals=prepare_asset(b,cfg)
        directory=out/asset;directory.mkdir()
        for name,frame in [("features",f.reset_index()),("state_probabilities",states),
                           ("training_events",fits),("targets",weights.reset_index()),("channel_signals",signals)]:
            write_csv(directory/(name+".csv"),frame)
        write_json(directory/"model_snapshots.json",snapshots)
        if bound:proof["states"].append(compare_states(bound[0],asset,states,fits,snapshots))
        for segment,(lo,hi) in SEGMENTS.items():
            s=states[states.date.between(lo,hi)];t=fits[fits.decision_date.between(lo,hi)]
            diagnostics.append({"asset":asset,"segment":segment,"observations":len(s),"refits":len(t),
                                "failed_refits":int(t.status.ne("ok").sum()),"cash_request_days":int(s.status.ne("ok").sum())})
        for bps in (0,5,10):
            for rate in (0.,.03):
                case=f"cost-{bps:02d}_cash-{int(rate*100):02d}";folder=directory/case;folder.mkdir()
                ledgers={}
                for strategy in names():
                    ledger,decisions,trades=run_account(b.adjusted_close.loc[weights.index],weights[strategy],strategy,bps,rate)
                    ledgers[strategy]=ledger
                    for suffix,frame in [("ledger",ledger),("decisions",decisions),("trades",trades)]:
                        write_csv(folder/f"{strategy}_{suffix}.csv",frame)
                    if bound and strategy in ("buy_hold","vol_hold"):
                        result=compare_control(bound[0],asset,case,strategy,ledger)
                        if result:proof["controls"].append(result)
                    for segment,(lo,hi) in SEGMENTS.items():
                        selection=ledger[ledger.date.between(lo,hi)]
                        rows.append({"asset":asset,"segment":segment,"strategy":strategy,"cost_bps":bps,"cash_rate":rate,**metrics(selection)})
                dates=ledgers["buy_hold"].date
                for label,difference,exposure in primary_contrasts(ledgers):
                    for segment,(lo,hi) in SEGMENTS.items():
                        mask=dates.between(lo,hi)
                        for block in (20,63):
                            intervals.append({"asset":asset,"segment":segment,"comparison":label,"cost_bps":bps,"cash_rate":rate,
                                              "average_exposure_difference":float(exposure[mask].mean()),
                                              **paired_interval(difference[mask],block,RegimeConfig().bootstrap_samples,42)})
                if bps==5 and rate==0:base[asset]=ledgers
    summary=pd.DataFrame(rows);paired=pd.DataFrame(intervals);training=pd.DataFrame(diagnostics)
    write_csv(out/"metrics.csv",summary);write_csv(out/"paired_inference.csv",paired);write_csv(out/"training_summary.csv",training)
    write_json(out/"parent_equivalence.json",proof)
    plot_results(base,paired,out,data_kind)
    write_report(summary,paired,training,proof,out,data_kind)
    leaf=Path(__file__).resolve().parent;parent_code=leaf.parent
    manifest={"generated_utc":datetime.now(timezone.utc).isoformat(),"data_kind":data_kind,
              "input_sha256":source["bars_sha256"] if source else sha256_bytes(d.to_csv(index=False,float_format="%.17g",lineterminator="\n").encode()),
              "analyzed_closes_sha256":closes_hash(d),"protocol_sha256":sha256(out/"protocol.json"),
              "source":source or {"origin":"invented parent closes and independent invented OHLC envelopes"},
              "source_sha256":{p.name:sha256(p) for p in sorted(leaf.glob("*.py"))},
              "frozen_parent_source_sha256":{n:sha256(parent_code/n) for n in ("config.py","data.py","models.py","engine.py")},
              "python":platform.python_version(),"packages":{n:importlib.metadata.version(n) for n in ("numpy","pandas","scipy","scikit-learn","hmmlearn","joblib","threadpoolctl","matplotlib")},
              "artifacts":{p.relative_to(out).as_posix():sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}}
    write_json(out/"manifest.json",manifest)
    print(f"Completed {len(summary)} metrics, {len(paired)} paired intervals and {len(proof['controls'])} parent control checks",flush=True)
    return summary,paired,training


def sha256_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def plot_results(base,paired,out,kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys=protocol()["primary_strategies"];labels=["Buy & hold","Vol hold","Breakout","Vol breakout","HMM breakout","HMM + vol breakout"]
    title="SYNTHETIC — invented prices" if kind=="synthetic" else "PRIVATE — current-vintage historical experiment"
    fig,axes=plt.subplots(2,1,figsize=(11,8),layout="constrained")
    for ax,asset in zip(axes,ASSETS):
        for key,label in zip(keys,labels):
            l=base[asset][key];ax.plot(pd.to_datetime(l.date),l.nav/100000,label=label,lw=1.1)
        ax.set(title=asset,ylabel="Net wealth / initial NAV",yscale="log");ax.grid(alpha=.2)
    axes[0].legend(ncol=3,fontsize=8);fig.suptitle(title+"\n55-session channel · 5 bp one way · cash 0%")
    fig.savefig(out/"wealth.png",dpi=130);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout="constrained")
    comparisons=[a+" minus "+b for a,b in COMPARISONS]+["interaction"]
    labels2=["HMM increment with vol","Vol increment, no HMM","HMM increment, unit size","Vol increment with HMM","2×2 interaction"]
    for ax,asset in zip(axes,ASSETS):
        for block,offset,color in [(20,-.1,"#2467a4"),(63,.1,"#c46525")]:
            sub=paired[(paired.asset==asset)&(paired.segment=="full")&(paired.cost_bps==5)&(paired.cash_rate==0)&(paired.block_sessions==block)].set_index("comparison").loc[comparisons]
            y=np.arange(5)+offset
            # Draw intervals directly: percentile intervals need not contain the observed mean.
            ax.hlines(y,sub.lower_95*100,sub.upper_95*100,color=color,label=f"{block}-session blocks")
            ax.scatter(sub.annualized_mean_difference*100,y,color=color,s=20)
        ax.axvline(0,color="black",lw=.8);ax.set(yticks=np.arange(5),yticklabels=labels2,title=asset,xlabel="Annualized arithmetic return difference (pp)")
        ax.invert_yaxis();ax.grid(axis="x",alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle(title+"\nPaired 95% moving-block intervals · descriptive, no multiplicity correction")
    fig.savefig(out/"paired_intervals.png",dpi=130);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(11,7),layout="constrained")
    for ax,asset in zip(axes,ASSETS):
        for key,label in zip(keys[2:],labels[2:]):
            l=base[asset][key];ax.plot(pd.to_datetime(l.date),l.held_weight.rolling(126).mean(),label=label,lw=1)
        ax.set(title=asset,ylabel="126-session mean held exposure",ylim=(0,1));ax.grid(alpha=.2)
    axes[0].legend(ncol=2,fontsize=8);fig.suptitle(title+"\nExposure explains part of a return difference; intervals do not isolate alpha")
    fig.savefig(out/"exposure.png",dpi=130);plt.close(fig)


def write_report(summary,paired,training,proof,out,kind):
    lines=["# HMM + volatility-adjusted breakout: frozen transfer experiment","",
           "**SYNTHETIC DEMONSTRATION — invented OHLC, no market-performance evidence.**" if kind=="synthetic" else "**PRIVATE current-vintage historical experiment. Do not publish these data or derived findings.**","",
           "Question: does the unchanged parent HMM add value to a different trend signal beyond volatility sizing?",
           "Primary: symmetric 55-session prior-high/low channel; 20/100-session and pulse-55 rules are predeclared sensitivities. SPY is primary; QQQ uses identical rules. All 18 strategies, 6 cost/cash scenarios, 4 reporting periods and 5 primary contrasts are retained.","",
           "Signals form after close and frozen fractions fill at the next session close. Old units earn pre-fill returns; funded trades charge actual drift-adjusted notional. Accounts start cash in 2013, with no period resets. Cash sensitivity uses continuous ACT/365.25 interest. Adjusted OHLC are model total-return units; no intrabar execution or added dividend.","",
           "## Primary methods, full period, 5 bp and zero cash yield","",
           "|Asset|Method|Net total return|CAGR|Excess Sharpe|Max drawdown|Realized vol|Turnover/year|Mean held exposure|",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    base=summary[(summary.segment=="full")&(summary.cost_bps==5)&(summary.cash_rate==0)]
    for r in base[base.strategy.isin(protocol()["primary_strategies"])].itertuples():
        sharpe="undefined" if pd.isna(r.excess_sharpe) else f"{r.excess_sharpe:.3f}"
        lines.append(f"|{r.asset}|{r.strategy}|{r.total_return:.2%}|{r.cagr:.2%}|{sharpe}|{r.max_drawdown:.2%}|{r.annualized_volatility:.2%}|{r.annualized_turnover:.2f}|{r.average_held_weight:.2%}|")
    lines += ["","![Net wealth](wealth.png)","","## Primary paired comparisons, full period, 5 bp and zero cash yield","",
              "|Asset|Comparison|Block|Mean difference/year|95% interval|Held exposure difference|","|---|---|---:|---:|---|---:|"]
    for r in paired[(paired.segment=="full")&(paired.cost_bps==5)&(paired.cash_rate==0)].itertuples():
        lines.append(f"|{r.asset}|{r.comparison}|{r.block_sessions}|{r.annualized_mean_difference:.2%}|[{r.lower_95:.2%}, {r.upper_95:.2%}]|{r.average_exposure_difference:.2%}|")
    lines += ["","![Paired intervals](paired_intervals.png)","","![Exposure](exposure.png)","","## All predeclared window sensitivities, full period, 5 bp and zero cash yield","",
              "|Asset|Method|Net CAGR|Excess Sharpe|Drawdown|Exposure|","|---|---|---:|---:|---:|---:|"]
    for r in base.itertuples():
        s="undefined" if pd.isna(r.excess_sharpe) else f"{r.excess_sharpe:.3f}"
        lines.append(f"|{r.asset}|{r.strategy}|{r.cagr:.2%}|{s}|{r.max_drawdown:.2%}|{r.average_held_weight:.2%}|")
    lines += ["","## Training and equivalence","",f"Refit failures (nonoverlapping periods): {int(training[training.segment!='full'].failed_refits.sum())}; failure cash-request days: {int(training[training.segment!='full'].cash_request_days.sum())}.",
              f"Bound parent evidence: {proof['parent_bound']}; state/parameter comparisons: {len(proof['states'])}; control-ledger comparisons: {len(proof['controls'])}. See parent_equivalence.json for tolerances and exact byte checks.","",
              "## Interpretation and limitations","",
              "Intervals use 2,000 paired noncircular moving-block resamples (20 and 63 sessions, seed 42) of daily net-return differences, annualized as arithmetic means. They are not CAGR intervals or evidence of skill. The interaction is a descriptive difference-in-differences, not a causal estimate. Exposure differences and cash interest can explain apparent improvement. Multiple comparisons are not adjusted.",
              "2013–2017 development, 2018–2020 validation and 2021–2025 historical confirmation are retrospective reporting labels; the parent history was already inspected. Neither QQQ nor these periods are independent unseen samples. Adjustments are current-vintage and not point-in-time. Synthetic OHLC envelopes have no market calibration.",
              "The state gate continuously overlays an independent channel latch. It can reenter after gate recovery without a new breakout; pulse-55 separately reveals dependence on a one-day signal interpretation. Volatility is the same past-20-day log-return estimator, not ATR. Long/cash only, no leverage, intrabar stop, tax, funding spread or market impact model.",
              "Complete metrics.csv retains 864 rows and paired_inference.csv retains 480 rows, including all losing and nonsignificant cases. There is no winner selection or rule tuning after this transfer.",""]
    (out/"REPORT.md").write_bytes("\n".join(lines).encode())
