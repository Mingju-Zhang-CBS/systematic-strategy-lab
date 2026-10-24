"""Fixed-protocol real-data study, machine-readable evidence and original figures."""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from .real_data import DATA, FUNDS, load_snapshot
from .real_research import RealConfig, backtest_real, real_metrics, paired_inference
from .runtime import Measurement, dump, manifest, require_empty_output

MODES = ("momentum", "risk_matched_static", "C_buy_hold", "G_buy_hold")
NAMES = {"momentum": "Momentum", "risk_matched_static": "Shared-risk-budget static", "C_buy_hold": "C buy & hold", "G_buy_hold": "G reserve"}
COLORS = {"momentum": "#167d8d", "risk_matched_static": "#b67535", "C_buy_hold": "#5c6294", "G_buy_hold": "#6e7f75"}


def section(ledger, bounds):
    return ledger.loc[ledger.date.between(*bounds)].reset_index(drop=True)


def charts(out, runs, windows, intervals, sensitivity, yearly):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "figure.facecolor": "#fbfaf7",
                         "axes.facecolor": "#fbfaf7", "savefig.facecolor": "#fbfaf7"})
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.6), sharex=True, layout="constrained", height_ratios=[2,1])
    for mode, ledger in runs.items():
        wealth = np.r_[1., np.cumprod(1+ledger["return"].to_numpy())]
        dates = pd.to_datetime(ledger.date)
        axes[0].plot(dates, wealth[1:], label=NAMES[mode], color=COLORS[mode], lw=1.7)
        axes[1].plot(dates, (wealth/np.maximum.accumulate(wealth)-1)[1:], color=COLORS[mode], lw=1.2)
    for ax in axes:
        ax.axvspan(pd.Timestamp("2020-01-01"), pd.Timestamp("2025-12-31"), color="#36b3a8", alpha=.08)
        ax.axvline(pd.Timestamp("2015-01-01"), color="#738091", ls="--", lw=.8)
        ax.axvline(pd.Timestamp("2020-01-01"), color="#738091", ls="--", lw=.8)
        ax.grid(alpha=.17)
    axes[0].set(yscale="log", ylabel="Wealth / initial capital (log scale)", title="01 / REAL NAVS, MODELED ALLOCATIONS\nFixed rules · 3 bp per gross dollar traded · 2-session posting delay")
    axes[0].legend(loc="upper left", ncol=2, fontsize=9)
    axes[1].set(ylabel="Drawdown", xlabel="Valuation date · shaded: chronological confirmation, 2020–2025")
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    fig.savefig(out/"performance.png", dpi=170); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10,5.3), layout="constrained")
    for i, name in enumerate(windows):
        for j, block in enumerate((20,63)):
            r = intervals[name][str(block)]
            y = i+(j-.5)*.18
            ax.plot([r["ci95_low"],r["ci95_high"]], [y,y], color="#167d8d" if j==0 else "#b67535", lw=3, alpha=.8)
            ax.scatter(r["annualized_log_return_difference"], y, color="#101928", s=24, zorder=3)
    ax.axvline(0, color="#738091", ls="--")
    ax.set(yticks=range(len(windows)), yticklabels=[n.title() for n in windows], xlabel="Annualized paired log-return difference: momentum − static", title="02 / WHAT SURVIVES UNCERTAINTY?\n95% moving-block intervals · teal: 20 sessions · amber: 63 sessions")
    ax.xaxis.set_major_formatter(PercentFormatter(1)); ax.grid(axis="x",alpha=.2)
    fig.savefig(out/"uncertainty.png", dpi=170); plt.close(fig)

    d = runs["momentum"]
    fig, ax = plt.subplots(figsize=(11,4.8), layout="constrained")
    palette = ["#d6dcda", "#7a97b8", "#167d8d", "#b67535", "#64608f"]
    ax.stackplot(pd.to_datetime(d.date),*[d[f"weight_{f}"] for f in FUNDS], labels=list(FUNDS), colors=palette)
    ax.set(ylim=(0,1),ylabel="Post-posting portfolio weight",xlabel="Valuation date",title="03 / THE RESERVE IS AN ASSET\nWhole-percent targets; realized weights drift between monthly transfers")
    ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.legend(ncol=5,loc="upper left")
    fig.savefig(out/"allocation.png",dpi=170);plt.close(fig)

    tab = pd.DataFrame(sensitivity)
    fig, ax = plt.subplots(figsize=(8.8,4.8),layout="constrained")
    for delay, g in tab.groupby("execution_delay"):
        ax.plot(g.cost_bps,g.confirmation_paired_annual_log_difference,marker="o",label=f"{delay} NAV sessions after observation")
    ax.axhline(0,color="#738091",ls="--",lw=1)
    ax.set(xlabel="Hypothetical friction per gross traded dollar (bp)",ylabel="Momentum − static, annualized log return",title="04 / EXECUTION DOES NOT COME FREE\nAll nine predefined stresses · chronological confirmation, 2020–2025")
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2);ax.legend(fontsize=9)
    fig.savefig(out/"cost_delay.png",dpi=170);plt.close(fig)

    fig, ax = plt.subplots(figsize=(11,4.5),layout="constrained")
    ys = pd.DataFrame(yearly)
    a=ys.loc[ys.strategy=="momentum"].set_index("year")
    b=ys.loc[ys.strategy=="risk_matched_static"].set_index("year")
    delta=a.total_return-b.total_return
    ax.bar(delta.index.astype(str),delta.values,color=["#167d8d" if v>=0 else "#b67535" for v in delta])
    ax.axhline(0,color="#738091",lw=1)
    ax.set(ylabel="Difference in within-year total return",xlabel="Continuous simulation · 2004 is a partial year",title="05 / A RESULT IS NOT A CONSTANT\nMomentum − static · same risk budget, costs and posting assumptions")
    ax.yaxis.set_major_formatter(PercentFormatter(1));ax.tick_params(axis="x",rotation=45);ax.grid(axis="y",alpha=.15)
    fig.savefig(out/"yearly.png",dpi=170);plt.close(fig)


def run_real(output):
    out = require_empty_output(output)
    data, source, protocol = load_snapshot()
    cfg = RealConfig()
    # Fail if code defaults have drifted away from the pre-result protocol.
    checks = {"lookback": "lookback_sessions", "skip": "skip_sessions", "covariance": "covariance_sessions",
              "vol_target": "annual_volatility_target", "asset_cap": "risky_asset_cap", "risky_cap": "risky_gross_cap",
              "publication_lag": "available_after_complete_sessions", "execution_delay": "base_execution_delay_from_observation_sessions",
              "cost_bps": "cost_bps", "initial_nav": "initial_capital", "start": "evaluation_start"}
    if any(getattr(cfg,key) != protocol[value] for key,value in checks.items()):
        raise ValueError("Configuration differs from frozen research protocol")
    windows = {"full": [cfg.start, protocol["data_end"]], **protocol["segments"]}
    runs, metrics, intervals, yearly, sensitivities = {}, {}, {}, [], []
    with Measurement() as measured:
        for mode in MODES:
            ledger, decisions, orders = backtest_real(data,cfg,mode)
            runs[mode] = ledger
            folder=out/mode; folder.mkdir()
            for name, frame in (("ledger",ledger),("decisions",decisions),("orders",orders)):
                frame.to_csv(folder/f"{name}.csv",index=False,float_format="%.12g")
            for name, bounds in windows.items():
                metrics.setdefault(name,{})[mode] = real_metrics(section(ledger,bounds))
            for year, group in ledger.groupby(ledger.date.str[:4]):
                yearly.append({"year":year,"strategy":mode,**real_metrics(group)})
        for name, bounds in windows.items():
            intervals[name] = {str(block):paired_inference(section(runs["momentum"],bounds),section(runs["risk_matched_static"],bounds),block=block) for block in (20,63)}
        for delay in protocol["sensitivity_execution_delays"]:
            for bps in protocol["sensitivity_cost_bps"]:
                stress=replace(cfg,execution_delay=delay,cost_bps=bps)
                a = runs["momentum"] if stress==cfg else backtest_real(data,stress,"momentum")[0]
                b = runs["risk_matched_static"] if stress==cfg else backtest_real(data,stress,"risk_matched_static")[0]
                ar=section(a,windows["confirmation"]);br=section(b,windows["confirmation"])
                sensitivities.append({"execution_delay":delay,"cost_bps":bps,
                                      "confirmation_momentum_return":real_metrics(ar)["total_return"],
                                      "confirmation_static_return":real_metrics(br)["total_return"],
                                      "confirmation_paired_annual_log_difference":float((np.log1p(ar["return"])-np.log1p(br["return"])).mean()*252)})
    pd.DataFrame(yearly).to_csv(out/"yearly.csv",index=False,float_format="%.12g")
    pd.DataFrame(sensitivities).to_csv(out/"sensitivity.csv",index=False,float_format="%.12g")
    pd.DataFrame([{"window":w,"strategy":s,**m} for w,strategies in metrics.items() for s,m in strategies.items()]).to_csv(out/"summary.csv",index=False,float_format="%.12g")
    dump(out/"metrics.json",{"data_kind":"public-real","instrument_kind":"accumulation_fund_nav",
                              "windows":metrics,"paired_inference":intervals,"sensitivity":sensitivities,"measurement":measured.result})
    dump(out/"protocol.json",protocol);dump(out/"source.json",source)
    charts(out,runs,windows,intervals,sensitivities,yearly)
    table=[]
    for window in windows:
        for mode in MODES:
            m=metrics[window][mode]
            sharpe=f"{m['excess_sharpe']:.3f}" if m["excess_sharpe"] is not None else "n/a"
            table.append(f"|{window}|{NAMES[mode]}|{m['total_return']:.2%}|{m['annualized_return']:.2%}|{sharpe}|{m['max_drawdown']:.2%}|{m['annual_gross_turnover']:.2f}×|")
    interval_table=[]
    for name in windows:
        for block in (20,63):
            r=intervals[name][str(block)]
            interval_table.append(f"|{name}|{block}|{r['annualized_log_return_difference']:.2%}|[{r['ci95_low']:.2%}, {r['ci95_high']:.2%}]|{'yes' if r['includes_zero'] else 'no'}|")
    report = """# Real multi-asset NAV allocation study

**Data:** official public TSP fund share NAV facts, 2 June 2003–31 December 2025; current historical vintage captured in October 2026. **Results:** modeled allocations on real fund NAVs, not observed trades or ETF returns. Investment income and operating expenses are embedded in NAV; cash dividends added separately: **zero**.

## Read the comparison

Momentum and static use identical trailing covariance scaling, whole-percent targets, risk limits, initial G holdings, posting delays and costs. The control shares the risk budget; realized volatility need not match. C and G buy-and-hold contextualize opportunity cost. All start with $100,000 in G at the previous supplied NAV. Three basis points apply to every gross dollar bought or sold, including G: moving between two funds incurs both legs. This is a hypothetical friction stress, not a measured TSP charge.

|Window|Strategy|Total return|Annualized return|Excess Sharpe vs G|Maximum drawdown|Annual gross turnover|
|---|---|---:|---:|---:|---:|---:|
""" + "\n".join(table) + """

![Real NAV performance and drawdown](performance.png)

## Chronological validation and uncertainty

Development: July 2004–2014; validation: 2015–2019; confirmation: 2020–2025. Rules were recorded before this implementation calculated returns. No threshold, asset set or stress row is chosen using these results. Covariance is re-estimated strictly from trailing observations, while the specification remains fixed. Holdings continue across boundaries and years, without favorable reset dates. These are historical temporal checks; familiar markets and current-vintage revisions prevent a claim of genuinely unseen, prospective out-of-sample evidence.

The primary comparison is the annualized mean **paired daily log-return difference**, not a CAGR spread or regression alpha. Overlapping moving blocks preserve local serial dependence; 2,000 deterministic resamples, seed 20261023. The two block lengths are both retained. Percentile intervals are descriptive and depend on stationarity and block choice; they do not correct for the wider history of strategy discovery.

|Window|Block sessions|Annual log-return difference|95% interval|Contains zero?|
|---|---:|---:|---:|---|
""" + "\n".join(interval_table) + """

![Paired uncertainty](uncertainty.png)

![Annual comparison](yearly.png)

## Information and funding clocks

The signal uses observations through date t, with momentum from t−252 through t−21 and covariance through t. A full intervening NAV session is allowed for publication. Targets become frozen after that intervening session, and a request is modeled at 11:00 New York time on t+2, ordinarily posting at that day's closing NAV. The posting NAV is unknown when target percentages are frozen. No exact historical publication timestamp is claimed; outages, corrections and delayed postings are not reconstructed. Delays of 2, 3 and 5 supplied sessions are all reported. Supplied valuation sessions are never forward-filled.

At a month boundary, the previous month's last observation is recognized by the next supplied session; no next-session price enters the signal. Targets are equal allocations across positive-momentum risky funds F/C/S/I, at most 50% per risky fund and 99% risky gross; trailing 126-session covariance scales down toward 10% annual volatility, without leverage. Risky weights are floored to whole percentage points, with the remainder in G. These are target limits, not continuous realized-weight constraints. Posting-month transfer counts never exceed two in the modeled runs. TSP access restrictions and processing rules mean this is an allocation study, not a participant-account replica.

![Allocation path](allocation.png)

Fees are funded by solving V_after + fee = V_before, with fee proportional to absolute changes in all five dollar holdings. Fractional units are then assigned at the posting NAV. Each day reconciles prior value + embedded-income price P&L − fees = ending value, with no external capital. G earns its observed fund return; it is not an extra cash-interest credit. Taxes, deposits, withdrawals, participant fees, unit rounding and exceptional postings are outside scope. The I Fund changed benchmark during 2024; its realized history is not a constant-index backfill.

![All predefined cost and delay scenarios](cost_delay.png)

## Evidence files and limits

`summary.csv`, `yearly.csv`, `sensitivity.csv`, `metrics.json` and per-strategy ledgers, decisions and orders expose every comparison. Costs use gross two-leg notional, not half-turnover. Annualization uses 252 supplied observations and drawdown includes each window's starting capital. Window metrics are sliced from a continuous simulation and are not separately reoptimized.

`protocol.json` records the pre-result specification; `source.json` identifies the snapshot and rights basis; `manifest.json` binds package sources, data, configuration, environment and all generated files. Public numerical facts are transcribed with attribution; no vendor ETF data, index levels, government logos, course code or employer material is included. See [data rights](../../DATA_RIGHTS.md), [methods](../../docs/METHODS.md) and [limitations](../../docs/PROVENANCE.md). Negative results and intervals containing zero are retained. This study does not establish capacity, exchange fills or tradable alpha.
"""
    c=metrics["confirmation"]
    interval=intervals["confirmation"]["20"]
    finding=(f"**Main finding:** In 2020–2025, momentum returned {c['momentum']['total_return']:.2%} "
             f"versus {c['risk_matched_static']['total_return']:.2%} for the static control. "
             f"Its annualized paired log-return difference was {interval['annualized_log_return_difference']:.2%}, "
             f"with a 20-session block 95% interval [{interval['ci95_low']:.2%}, {interval['ci95_high']:.2%}]. "
             f"Both prespecified interval lengths contain zero: {all(intervals['confirmation'][str(b)]['includes_zero'] for b in (20,63))}. "
             "The confirmation evidence does not establish an incremental momentum advantage.")
    report=report.replace("## Read the comparison",finding+"\n\n## Read the comparison")
    (out/"REPORT.md").write_text(report,encoding="utf-8")
    files={str(p.relative_to(out)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob("*")) if p.is_file()}
    record=manifest(asdict(cfg),source["dataset_sha256"],"public-real")
    record.update({"protocol_sha256":hashlib.sha256((DATA/"protocol.json").read_bytes()).hexdigest(),
                   "source_record_sha256":hashlib.sha256((DATA/"source.json").read_bytes()).hexdigest(),
                   "outputs_sha256":files,"calendar_note":"Supplied official valuation sessions; no price filling or fabricated holiday returns."})
    dump(out/"manifest.json",record)
    print(json.dumps({"data_rows":len(data),"evaluation_rows_per_strategy":len(runs['momentum']),"confirmation":intervals['confirmation'],"measurement":measured.result},indent=2))
