"""Fixed method/scenario reports and reproducible source/input/output records."""
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from .config import AllocationConfig,ASSETS,METHODS,SEGMENTS,COMPARISONS,variants
from .data import wide_prices
from .research import make_targets
from .engine import backtest,metrics
from ..regimes.engine import paired_interval
from ..runtime import require_empty_output


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def write_csv(path,frame):frame.to_csv(path,index=False,float_format="%.17g",lineterminator="\n")


def protocol(cfg=AllocationConfig()):
    cfg.validate()
    return {"version":"allocation-v1","config":asdict(cfg),"assets":list(ASSETS),"methods":list(METHODS),
            "variants":[{"name":name,"method":method,"config":asdict(c),"reversed_views":rev} for name,method,c,rev in variants(cfg)],
            "segments":SEGMENTS,"cost_bps":[0,5,10],"continuous_cash_rates":[0.,.03],
            "comparisons":COMPARISONS,"bootstrap_blocks":[20,63],
            "inputs":"2009–2025 adjusted closes; current-vintage real inputs private",
            "estimation":"Trailing arithmetic daily returns through decision close t, annualized by 252",
            "execution":"Frozen target fraction after close t, funded execution at close t+1",
            "bl_prior":"risk_aversion * covariance * equal-weight reference; NOT observed market-cap weights",
            "bl_views":"one named absolute annual arithmetic return view per asset, trailing sample mean; reversed-view sensitivity",
            "bl_risk":"Use shared covariance for optimization; posterior uncertainty is diagnostic only",
            "risk_budget":"convex positive-exposure log-barrier objective with homogeneous weight-cap constraints",
            "return_tilt":"dimensionless linear reward added to risk-budget objective; RRP-inspired, not a canonical relaxed-RP replication",
            "perturbations":"4 fixed seed/date-normal shocks, scaled by sqrt(252*diag(annual_cov)/lookback); IID stress magnitude, not a confidence interval",
            "failure":"request all cash at that scheduled rebalance; preserve cause and one-session fill delay",
            "inference":"descriptive paired arithmetic-return means; no multiplicity adjustment or prospective alpha claim"}


def run_study(frame,output,cfg=AllocationConfig(),data_kind="synthetic",source=None,input_hash=None):
    if data_kind not in {"synthetic","private-real-current-vintage"}:raise ValueError("Explicit known data kind required")
    cfg.validate();prices=wide_prices(frame);out=require_empty_output(output)
    write_json(out/"protocol.json",protocol(cfg))
    print(data_kind+": estimating fixed allocation specifications",flush=True)
    targets,events,snapshots,perturbations=make_targets(prices,cfg)
    for name,table in targets.items():write_csv(out/(name+"_targets.csv"),table.reset_index())
    write_csv(out/"optimization_events.csv",events);write_json(out/"parameter_snapshots.json",snapshots)
    write_csv(out/"forecast_perturbations.csv",perturbations)
    diagnostics=[];robust=[]
    for segment,(lo,hi) in SEGMENTS.items():
        for variant,group in events[events.decision_date.between(lo,hi)].groupby("variant",sort=False):
            ok=group[group.status.eq("ok")]
            diagnostics.append({"segment":segment,"variant":variant,"decisions":len(group),
                                "failed_decisions":int(group.status.ne("ok").sum()),
                                "mean_risk_fraction_l2":float(ok.risk_fraction_l2.mean()) if len(ok) else None,
                                "mean_predicted_target_vol":float(ok.predicted_target_vol.mean()) if len(ok) else None,
                                "maximum_optimality_residual":float(ok.optimality_residual.max()) if len(ok) else None})
        for method,group in perturbations[perturbations.decision_date.between(lo,hi)].groupby("method",sort=False):
            ok=group[group.status.eq("ok")]
            robust.append({"segment":segment,"method":method,"perturbations":len(group),"failures":int(group.status.ne("ok").sum()),
                           "median_sleeve_half_l1":float(ok.sleeve_half_l1.median()) if len(ok) else None,
                           "p95_sleeve_half_l1":float(ok.sleeve_half_l1.quantile(.95)) if len(ok) else None,
                           "median_target_half_l1":float(ok.target_half_l1.median()) if len(ok) else None})
    diagnostics=pd.DataFrame(diagnostics);robust=pd.DataFrame(robust)
    write_csv(out/"optimization_summary.csv",diagnostics);write_csv(out/"perturbation_summary.csv",robust)
    records=[];paired=[];base={};start=next(iter(targets.values())).index[0]
    evaluation=prices.loc[start:]
    for bps in (0,5,10):
        for rate in (0.,.03):
            name=f"cost-{bps:02d}_cash-{int(rate*100):02d}";destination=out/name;destination.mkdir()
            ledgers={}
            for variant,table in targets.items():
                ledger,decisions,trades=backtest(evaluation,table,cfg.initial_nav,bps,rate)
                write_csv(destination/f"{variant}_ledger.csv",ledger)
                write_csv(destination/f"{variant}_decisions.csv",decisions)
                write_csv(destination/f"{variant}_trades.csv",trades)
                if variant in METHODS:ledgers[variant]=ledger
                for segment,(lo,hi) in SEGMENTS.items():
                    selection=ledger[ledger.date.between(lo,hi)]
                    if selection.empty:raise ValueError("Missing frozen evaluation segment")
                    records.append({"segment":segment,"variant":variant,"cost_bps":bps,"cash_rate":rate,**metrics(selection)})
            for segment,(lo,hi) in SEGMENTS.items():
                for alternative,control in COMPARISONS:
                    a=ledgers[alternative];b=ledgers[control];mask=a.date.between(lo,hi)
                    difference=(a.loc[mask,"return"]-b.loc[mask,"return"]).to_numpy()
                    exposure=float(a.loc[mask,"held_exposure"].mean()-b.loc[mask,"held_exposure"].mean())
                    for block in (20,63):
                        paired.append({"segment":segment,"alternative":alternative,"control":control,"cost_bps":bps,"cash_rate":rate,
                                       "average_exposure_difference":exposure,**paired_interval(difference,block,cfg.bootstrap_samples,cfg.seed)})
            if bps==5 and rate==0:base=ledgers
    summary=pd.DataFrame(records);inference=pd.DataFrame(paired)
    write_csv(out/"metrics.csv",summary);write_csv(out/"paired_inference.csv",inference)
    plot_results(base,robust,events,out,data_kind)
    write_report(summary,inference,diagnostics,robust,out,data_kind)
    package=Path(__file__).resolve().parent
    input_hash=input_hash or hashlib.sha256(frame.to_csv(index=False,float_format="%.17g",lineterminator="\n").encode()).hexdigest()
    manifest={"generated_utc":datetime.now(timezone.utc).isoformat(),"data_kind":data_kind,"input_sha256":input_hash,
              "protocol_sha256":sha256(out/"protocol.json"),"source":source or {"origin":"independently invented factor fixture; not actual ETF prices"},
              "source_sha256":{p.name:sha256(p) for p in sorted(package.glob("*.py"))},
              "shared_code_sha256":{"regimes/engine.py":sha256(package.parent/"regimes/engine.py"),"runtime.py":sha256(package.parent/"runtime.py")},
              "python":platform.python_version(),"packages":{n:importlib.metadata.version(n) for n in ["numpy","pandas","scipy","scikit-learn","threadpoolctl","matplotlib"]},
              "artifacts":{p.relative_to(out).as_posix():sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}}
    write_json(out/"manifest.json",manifest)
    print(f"Completed {len(summary)} metric rows, {len(inference)} paired rows; {len(targets)*6} accounts",flush=True)
    return summary,inference,diagnostics,robust


def plot_results(ledgers,robust,events,out,kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor":"#f5f1e9","axes.facecolor":"#f5f1e9","text.color":"#101928","font.size":10})
    label="SYNTHETIC — invented inputs" if kind=="synthetic" else "PRIVATE — current-vintage Yahoo reference"
    colors=["#101928","#83919e","#bd7950","#4274a0","#826899","#22998f"]
    fig,axes=plt.subplots(2,1,figsize=(11,8),layout="constrained")
    for method,color in zip(METHODS,colors):
        d=ledgers[method];dates=pd.to_datetime(d.date)
        axes[0].plot(dates,d.nav/100000,label=method.replace("_"," "),color=color,lw=1.3)
        axes[1].plot(dates,d.held_exposure,label=method,color=color,lw=1.)
    axes[0].set_ylabel("Model wealth / initial wealth");axes[1].set_ylabel("Held risky fraction")
    axes[0].legend(ncol=3,fontsize=8);axes[1].set_ylim(0,1.05)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(label+"\nSix bounded methods; 5 bp traded-dollar cost, 0% cash",fontsize=13)
    fig.savefig(out/"wealth_and_exposure.png",dpi=160);plt.close(fig)
    selected=robust[robust.segment.eq("full")].set_index("method").reindex(METHODS)
    fig,ax=plt.subplots(figsize=(11,4.8),layout="constrained")
    x=np.arange(len(METHODS));ax.bar(x,selected.median_sleeve_half_l1*100,color=colors)
    ax.scatter(x,selected.p95_sleeve_half_l1*100,label="95th percentile",color="#101928",marker="_")
    ax.set_xticks(x,[m.replace("_","\n") for m in METHODS],fontsize=9)
    ax.set_ylabel("Sleeve half-L1 weight change (percentage points)");ax.legend();ax.grid(axis="y",alpha=.2)
    ax.set_title(label+"\nControlled mean perturbations; fixed covariance, no winner selection")
    fig.savefig(out/"forecast_sensitivity.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.8),layout="constrained")
    primary=events[events.variant.isin(METHODS)&events.status.eq("ok")]
    positions=np.arange(5);width=.12
    for j,(method,color) in enumerate(zip(METHODS,colors)):
        means=primary[primary.variant.eq(method)][["risk_fraction_"+a for a in ASSETS]].mean().to_numpy()
        ax.bar(positions+(j-2.5)*width,means,width,label=method.replace("_"," "),color=color)
    ax.axhline(.2,ls="--",color="#101928",lw=1);ax.set_xticks(positions,ASSETS)
    ax.set_ylabel("Mean estimated sleeve risk fraction");ax.grid(axis="y",alpha=.2);ax.legend(ncol=3,fontsize=8)
    ax.set_title(label+"\nEstimated risk contributions; caps can prevent equal risk budgets")
    fig.savefig(out/"risk_contributions.png",dpi=160);plt.close(fig)


def write_report(metrics,inference,diagnostics,robust,out,kind):
    label="SYNTHETIC / INVENTED INPUTS" if kind=="synthetic" else "PRIVATE / REAL CURRENT-VINTAGE REFERENCE"
    lines=[f"# Robust asset allocation — {label}","",
           "How do return-driven and risk-driven allocations respond to noisy forecasts, concentration limits and implementation costs?","",
           "Five ETF roles: SPY, EFA, IEF, GLD, DBC. Public results are invented; real adjusted-price research remains private. "
           "These are funded fractional total-return-unit accounts, not observed ETF shares or fills.","",
           "## Fixed comparison","",
           "Six primary methods share trailing data, 40% sleeve asset caps, a 10% target-volatility scaling rule, "
           "21-session rebalancing and next-session-close execution. BL changes the mean, not the common covariance. "
           "Its prior is reverse-implied from an equal-weight reference, not historical market-cap weights. "
           "Return-tilted risk budgeting is a dimensionless convex RRP-inspired specification, not a replication of a uniquely defined canonical relaxed-RP model.","",
           "## Historical confirmation: 2021–2025","","Base scenario: 5 bp per dollar traded, 0% assumed cash yield.","",
           "| Method | CAGR | Excess Sharpe | Max drawdown | Annual turnover | Held risky exposure | Effective risky assets |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    base=metrics[(metrics.segment=="confirmation")&(metrics.cost_bps==5)&(metrics.cash_rate==0)]
    for method in METHODS:
        r=base[base.variant.eq(method)].iloc[0];sharpe="undefined" if pd.isna(r.excess_sharpe) else f"{r.excess_sharpe:.2f}"
        ena="undefined" if pd.isna(r.average_effective_assets) else f"{r.average_effective_assets:.2f}"
        lines.append(f"| {method} | {r.cagr:.2%} | {sharpe} | {r.max_drawdown:.2%} | {r.annualized_turnover:.2f}x | {r.average_held_exposure:.1%} | {ena} |")
    lines += ["","![Wealth and actual held exposure](wealth_and_exposure.png)","","## Predeclared paired comparisons","",
              "| Alternative minus control | Block sessions | Annualized paired arithmetic mean | 95% interval | Exposure difference |",
              "|---|---:|---:|---:|---:|"]
    selected=inference[(inference.segment=="confirmation")&(inference.cost_bps==5)&(inference.cash_rate==0)]
    for r in selected.itertuples():
        lines.append(f"| {r.alternative} minus {r.control} | {r.block_sessions} | {r.annualized_mean_difference:.2%} | [{r.lower_95:.2%}, {r.upper_95:.2%}] | {r.average_exposure_difference:.1%} |")
    lines += ["","These are 252 times aligned arithmetic daily-return differences, not CAGR differences. "
              "20/63-session moving-block percentile intervals are descriptive, without multiplicity adjustment. "
              "Shared risk procedures need not create identical realized risk or exposure. Familiar historical windows are not independently unseen future evidence.","",
              "## Controlled forecast fragility","",
              "Covariance stays fixed while four date-seeded normal mean shocks are applied per rebalance. "
              "Their scale is an IID standard-error approximation used only as a declared stress size, not a confidence interval. "
              "Mean-independent methods intentionally have zero sensitivity in this test; that does not prove superior future returns.","",
              "| Method | Median sleeve half-L1 change | 95th percentile | Failed perturbations |","|---|---:|---:|---:|"]
    for r in robust[robust.segment.eq("full")].itertuples():
        lines.append(f"| {r.method} | {r.median_sleeve_half_l1:.2%} | {r.p95_sleeve_half_l1:.2%} | {r.failures} |")
    lines += ["","![Forecast sensitivity](forecast_sensitivity.png)","","## Risk budgeting and solver failures","",
              "![Estimated risk fractions](risk_contributions.png)","",
              "Equal capital weights do not imply equal risk. A 40% asset cap can prevent exact equal-risk contributions; "
              "the risk-budget residual is reported rather than relabeling a constrained solution as exact risk parity.","",
              "| Primary method | Scheduled decisions | Failed decisions | Mean risk-fraction L2 error | Maximum optimality residual |",
              "|---|---:|---:|---:|---:|"]
    for r in diagnostics[(diagnostics.segment=="full")&diagnostics.variant.isin(METHODS)].itertuples():
        error="undefined" if pd.isna(r.mean_risk_fraction_l2) else f"{r.mean_risk_fraction_l2:.4g}"
        residual="undefined" if pd.isna(r.maximum_optimality_residual) else f"{r.maximum_optimality_residual:.3g}"
        lines.append(f"| {r.variant} | {r.decisions} | {r.failed_decisions} | {error} | {residual} |")
    lines += ["","Failures request all cash until the next scheduled rebalance; execution is still delayed one session. "
              "Success flags alone are insufficient: quadratic objectives have a capped-simplex first-order gap check; "
              "risk-budget objectives have primal/dual stationarity and complementarity diagnostics. Failures remain in evaluation dates and event records.","",
              "## Every fixed specification","",
              "All six methods have sample-covariance and 252-session-window sensitivities. Additional cases retain "
              "BL confidence 25%/75%, reversed views and return-tilt strength 0.25/1.0. No case is selected by performance.","",
              "| Specification | Confirmation CAGR | Confirmation excess Sharpe |","|---|---:|---:|"]
    for r in base.itertuples():
        value="undefined" if pd.isna(r.excess_sharpe) else f"{r.excess_sharpe:.2f}"
        lines.append(f"| {r.variant} | {r.cagr:.2%} | {value} |")
    lines += ["","`metrics.csv` retains all 23 specifications × three costs × two cash assumptions × four periods "
              "(552 rows). `paired_inference.csv` retains 144 rows. Optimization events, parameters, risk fractions, "
              "forecast perturbations, all targets, decisions, trades and ledgers are generated. The full run has 138 accounts.","",
              "## Scope and interpretation","",
              "Weights and cash continue across development 2013–2017, validation 2018–2020 and historical confirmation 2021–2025. "
              "Transaction costs include first entry, both sides of rebalances and holding drift. There is no terminal invented liquidation. "
              "Cash earns assumed continuous 0% or 3% over calendar days. Adjusted prices already embed income; no dividend is added. "
              "ETF choice, current-vintage adjustments, correlation instability and the missing historical release archive limit inference. "
              "The original notebooks are references, not source code or performance evidence. No favorable outcome is required.",""]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
