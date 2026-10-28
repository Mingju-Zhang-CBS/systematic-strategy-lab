"""Offline synthetic or private-input exploratory curve study and audit report."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .engine import PRODUCTS
from .panel import prepare
from .research import ResearchProtocol, STRATEGIES, run_research
from .research_fixture import research_frames
from strategy_lab import __version__


def monthly_account(ledger, protocol, dates):
    expected = dates[(dates >= pd.Timestamp(protocol.start)) & (dates <= pd.Timestamp(protocol.end))]
    l = ledger.copy()
    l["session"] = pd.to_datetime(l.session)
    rows = []
    for month in pd.period_range(protocol.start, protocol.end, freq="M"):
        h = l[l.session.dt.to_period("M") == month]
        scope = expected[expected.to_period("M") == month]
        valid = len(h) == len(scope) and len(h) > 0 and not h.stale_contracts.any() and h.equity.iloc[-1] > 0
        rows.append(dict(month=str(month), return_=float(h.equity.iloc[-1]/h.opening_equity.iloc[0]-1) if valid else np.nan,
                         valid=valid, expected_sessions=len(scope), observed_sessions=len(h),
                         exposed_sessions=int((h.positions > 0).sum()), stale_sessions=int((h.stale_contracts > 0).sum())))
    return pd.DataFrame(rows)


def summarize(result, case):
    l, p = result["ledger"], result["protocol"]
    previous = np.r_[p["capital"], l.equity.to_numpy()[:-1]]
    returns = l.equity.to_numpy()/previous-1
    complete = not result["status"].startswith("failed") and not l.stale_contracts.any()
    equity = np.r_[p["capital"], l.equity.to_numpy()]
    annual = (equity[-1]/equity[0])**(252/len(l))-1 if complete and equity[-1] > 0 else np.nan
    volatility = float(np.std(returns, ddof=1)*np.sqrt(252)) if len(returns) > 1 else np.nan
    return dict(case=case, strategy=result["strategy"], status=result["status"], sessions=len(l), stop_date=l.session.iloc[-1],
                initial_capital=p["capital"], terminal_equity=equity[-1], observed_net_change=equity[-1]-equity[0],
                annual_return=annual, annual_volatility=volatility if complete else np.nan,
                net_sharpe=float(np.mean(returns)*252/volatility) if complete and volatility > 0 else np.nan,
                observed_max_drawdown=float(np.min(equity/np.maximum.accumulate(equity)-1)),
                worst_5pct_daily_mean=float(np.mean(np.sort(returns)[:max(1, int(np.ceil(.05*len(returns))))])),
                costs=float(result["trades"].cost.sum()), executed_legs=len(result["trades"]),
                contract_turnover=float(result["trades"].delta.abs().sum()),
                exposed_sessions=int((l.positions > 0).sum()), stale_sessions=int((l.stale_contracts > 0).sum()),
                max_gross_to_equity=float((l.gross_proxy/l.equity.where(l.equity > 0)).max()),
                max_reserve_to_equity=float((l.reserve/l.equity.where(l.equity > 0)).max()),
                reconciliation_error=result["reconciliation"]["terminal_error"])


def paired_inference(months, phases=None):
    """Predeclared paired noncircular blocks; missing/failed months never dropped."""
    rows = []
    if phases is None:
        phases = {"development":("2005-01", "2014-12"), "review":("2015-01", "2019-12"), "confirmation":("2020-01", "2025-12")}
    claims = {"bm_increment":("bm_outright", "half_mix"), "bm_spread_mean":("bm_spread", None)}
    for phase, (start, end) in phases.items():
        for block in (6, 12):
            group = []
            for claim, (left, right) in claims.items():
                a = months[left].set_index("month")
                b = months[right].set_index("month") if right else None
                required = pd.period_range(start, end, freq="M").astype(str)
                x = a.reindex(required)
                valid = x.valid.eq(True).all() and len(x) >= block
                if b is not None:
                    y = b.reindex(required)
                    valid = valid and y.valid.eq(True).all()
                if not valid:
                    row = dict(phase=phase, block=block, claim=claim, status="not_evaluable_incomplete_or_failed_months", months=len(x), mean=np.nan, lower=np.nan, upper=np.nan, p_value=np.nan)
                elif x.exposed_sessions.sum() == 0:
                    row = dict(phase=phase, block=block, claim=claim, status="not_evaluable_no_BM_exposure", months=len(x), mean=np.nan, lower=np.nan, upper=np.nan, p_value=np.nan)
                else:
                    values = x.return_.to_numpy()-(y.return_.to_numpy() if b is not None else 0)
                    mean = float(np.mean(values))
                    rng = np.random.default_rng(20261026)
                    starts = rng.integers(0, len(values)-block+1, size=(5000, int(np.ceil(len(values)/block))))
                    indices = (starts[:, :, None]+np.arange(block)).reshape(5000, -1)[:, :len(values)]
                    sampled = values[indices].mean(axis=1)
                    lower, upper = np.quantile(sampled, [.025, .975])
                    null = (values-mean)[indices].mean(axis=1)
                    probability = (1+int((np.abs(null) >= abs(mean)).sum()))/5001
                    row = dict(phase=phase, block=block, claim=claim, status="evaluated_historical_exploration", months=len(values),
                               mean=mean, lower=float(lower), upper=float(upper), p_value=probability)
                row["holm_p"] = np.nan
                group.append(row)
            # Keep the family size two even when only one claim is evaluable.
            order = sorted([i for i, r in enumerate(group) if np.isfinite(r["p_value"])], key=lambda i:group[i]["p_value"])
            last = 0.
            for rank, i in enumerate(order):
                last = max(last, min(1., (2-rank)*group[i]["p_value"]))
                group[i]["holm_p"] = last
            rows.extend(group)
    return pd.DataFrame(rows)


def write_result(result, output, detail):
    output.mkdir(parents=True, exist_ok=False)
    for name in ("ledger", "trades", "events")+(("decisions", "holdings", "pnl") if detail else ()):
        frame = result[name]
        if len(frame.columns):
            frame.to_csv(output/(name+".csv.gz"), index=False, compression={"method":"gzip", "mtime":0})
    receipt = {name:result[name] for name in ("strategy", "status", "protocol", "reconciliation")}
    (output/"RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def figures(tape, base, summary, inference, output):
    plt.rcParams.update({"figure.facecolor":"#faf8f3", "axes.facecolor":"#faf8f3", "axes.spines.top":False,
                         "axes.spines.right":False, "axes.labelcolor":"#101928", "font.size":9})
    nature = "PRIVATE real references" if tape.manifest["data_kind"] == "restricted" else "SYNTHETIC inputs"
    colors = ["#101928", "#36b3a8", "#b97b45", "#657ba5", "#b65565"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    for (name, r), color in zip(base.items(), colors):
        l, capital = r["ledger"], r["protocol"]["capital"]
        value = l.equity.to_numpy()/capital
        axes[0].plot(pd.to_datetime(l.session), value, label=name+(' [stopped]' if r["status"].startswith("failed") else ''), color=color)
        peak = np.maximum.accumulate(np.r_[1., value])[1:]
        axes[1].plot(pd.to_datetime(l.session), value/peak-1, color=color)
    axes[0].set(ylabel="Marked account / initial capital", title=nature+" · costs and proxy collateral · failed paths stop")
    axes[1].set(ylabel="Drawdown from prior peak")
    axes[0].legend(ncol=3, frameon=False)
    fig.savefig(output/"accounts_and_drawdowns.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True, constrained_layout=True)
    for (name, r), color in zip(base.items(), colors):
        l = r["ledger"]
        denominator = l.equity.where(l.equity > 0)
        axes[0].plot(pd.to_datetime(l.session), l.gross_proxy/denominator, color=color, label=name)
        axes[1].plot(pd.to_datetime(l.session), l.reserve/denominator, color=color)
    axes[0].axhline(3, color="grey", linestyle="--")
    axes[1].axhline(.5, color="grey", linestyle="--")
    axes[0].set(ylabel="Gross proxy / equity", title=nature+" · EOD limits are not intraday funding reconstruction")
    axes[1].set(ylabel="Model reserve / equity")
    axes[0].legend(ncol=5, frameon=False)
    fig.savefig(output/"funding_constraints.png", dpi=160)
    plt.close(fig)
    s = tape.selection.copy()
    s["year"] = pd.to_datetime(s.session).dt.year
    s["eligible"] = s.reason == "eligible"
    coverage = s.pivot_table(index="product", columns="year", values="eligible", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    im = ax.imshow(coverage, aspect="auto", vmin=0, vmax=1, cmap="YlGnBu")
    ax.set_yticks(range(len(coverage)), coverage.index)
    ax.set_xticks(range(0, len(coverage.columns), max(1, len(coverage.columns)//12)), coverage.columns[::max(1, len(coverage.columns)//12)])
    ax.set_title(nature+" · lagged liquid pairs admitted under declared evidence assumptions")
    fig.colorbar(im, ax=ax, label="Fraction of scheduled dates")
    fig.savefig(output/"pair_coverage.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, claim in zip(axes, ("bm_increment", "bm_spread_mean")):
        h = inference[inference.phase.isin(["confirmation", "synthetic_demo"]) & (inference.claim == claim)]
        for i, r in enumerate(h.itertuples(index=False)):
            if np.isfinite(r.mean):
                ax.hlines(i, r.lower*100, r.upper*100, color="#36b3a8")
                ax.plot(r.mean*100, i, "o", color="#101928")
            else:
                ax.text(.03, .3+.3*i, r.status.replace("_", " "), transform=ax.transAxes, fontsize=8)
        ax.axvline(0, color="grey", linestyle="--")
        ax.set_yticks(range(len(h)), [str(x)+"-month blocks" for x in h.block])
        ax.set(title=claim, xlabel="Mean monthly difference, percentage points")
    fig.suptitle(nature+" · paired 95% intervals; failed claims retained")
    fig.savefig(output/"paired_uncertainty.png", dpi=160)
    plt.close(fig)
    grid = summary.pivot(index="case", columns="strategy", values="annual_return")
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    im = ax.imshow(np.ma.masked_invalid(grid.to_numpy()*100), aspect="auto", cmap="RdBu", vmin=-15, vmax=15)
    ax.set_yticks(range(len(grid)), grid.index)
    ax.set_xticks(range(len(grid.columns)), grid.columns, rotation=20)
    ax.set_title(nature+" · full-window annualized results; blank = failed/stale, not zero")
    fig.colorbar(im, ax=ax, label="Annualized net return (%)")
    fig.savefig(output/"predeclared_sensitivities.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(4, 2, figsize=(11, 12), constrained_layout=True)
    snapshots = pd.to_datetime(["2008-09-15", "2014-11-28", "2020-04-20", "2022-03-08"])
    for product, ax in zip(PRODUCTS, axes.flat):
        for day in snapshots:
            index = tape.dates.searchsorted(day, side="right")-1
            if index < 0:
                continue
            maturity = tape.contracts.delivery
            mask = ((tape.contracts["product"] == product) & (maturity >= day) & (maturity <= day+pd.Timedelta(days=550)))
            cols = np.flatnonzero(mask)
            ax.plot((maturity.iloc[cols]-tape.dates[index]).dt.days, tape.prices[index, cols], label=str(tape.dates[index].date()), marker=".", linewidth=.8)
        ax.set(title=product, xlabel="Days to delivery month", ylabel="USD / physical unit")
    handles, labels = axes.flat[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4)
    fig.suptitle(nature+" · four predeclared curve dates · absent dates not backfilled", y=1.02)
    fig.savefig(output/"curve_snapshots.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true")
    mode.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-only", action="store_true", help="Smoke run only; not the full predeclared stress study")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    execution_code = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob("*.py")}
    if args.fixture:
        q, c, manifest = research_frames()
        protocol = ResearchProtocol(start="2021-01-01", end="2022-12-31")
    else:
        q = pd.read_csv(args.input/"quotes.csv.gz", parse_dates=["session"])
        c = pd.read_csv(args.input/"contracts.csv")
        manifest = json.loads((args.input/"manifest.json").read_text())
        protocol = ResearchProtocol()
        for name, expected in manifest.get("files", {}).items():
            if hashlib.sha256((args.input/name).read_bytes()).hexdigest() != expected:
                raise ValueError("private input fingerprint mismatch: "+name)
    cases = [("base", protocol, 5), ("zero_ticks", replace(protocol, slippage_ticks=0), 5),
             ("two_ticks", replace(protocol, slippage_ticks=2), 5),
             ("zero_friction", replace(protocol, commission=0, slippage_ticks=0), 5),
             ("reserve_20pct", replace(protocol, reserve_rate=.2), 5),
             ("delay_plus_1", replace(protocol, extra_delay=1), 5), ("delay_plus_3", replace(protocol, extra_delay=3), 5),
             ("exit_buffer_10", protocol, 10),
             ("exclude_energy", replace(protocol, exclude_sector="energy"), 5),
             ("exclude_metals", replace(protocol, exclude_sector="metals"), 5),
             ("exclude_agriculture", replace(protocol, exclude_sector="agriculture"), 5)]
    if args.base_only:
        cases = cases[:1]
    frozen = dict(created_utc=datetime.now(timezone.utc).isoformat(), manifest=manifest,
                  execution_code=execution_code, package_version=__version__, python=sys.version,
                  numpy=np.__version__, pandas=pd.__version__,
                  cases=[dict(name=name, protocol=asdict(p), exit_buffer=buffer) for name, p, buffer in cases],
                  methods="same-contract reference histories; daily known-boundary roll/risk control; monthly direction updates",
                  delay="postpone signal decision update; selection and risk use the later permitted observation, not a frozen-order latency replay",
                  sectors="remove sector requests without outcome-driven reranking",
                  data_kind=manifest["data_kind"])
    (args.output/"FROZEN_RUN.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print("Preparing once-validated snapshot", len(q), len(c), flush=True)
    tape = prepare(q, c, manifest)
    print("Prepared", len(tape.dates), "scheduled sessions; executing fixed experiments", flush=True)
    tape.selection.to_csv(args.output/"pair_selection.csv.gz", index=False, compression={"method":"gzip", "mtime":0})
    tape.off_calendar.to_csv(args.output/"off_calendar_records.csv.gz", index=False, compression={"method":"gzip", "mtime":0})
    tape.closures.to_csv(args.output/"scheduled_closures.csv", index=False)
    tape.monthly_returns.to_csv(args.output/"reference_months.csv", index=False)
    tape.signals.to_csv(args.output/"signal_candidates.csv", index=False)
    summary, base, monthly, yearly, all_events = [], {}, {}, [], []
    for case, p, buffer in cases:
        current = prepare(q, c, manifest, exit_buffer=10) if buffer == 10 else tape
        for name in list(STRATEGIES)+["trend_half", "carry_half"]:
            strategy = name.removesuffix("_half")
            config = replace(p, capital=p.capital/2) if name.endswith("_half") else p
            result = run_research(current, strategy, config, detail=case == "base")
            write_result(result, args.output/case/name, detail=case == "base")
            row = summarize(result, case)
            row["strategy"] = name
            summary.append(row)
            if not result["events"].empty:
                all_events.append(result["events"].assign(case=case, strategy=name))
            if case == "base":
                monthly[name] = monthly_account(result["ledger"], config, current.dates)
                if not name.endswith("_half"):
                    base[name] = result
                    l = result["ledger"].copy()
                    l["year"] = pd.to_datetime(l.session).dt.year
                    for year, h in l.groupby("year"):
                        yearly.append(dict(strategy=name, year=year, observed_return=h.equity.iloc[-1]/h.opening_equity.iloc[0]-1,
                                           sessions=len(h), final_date=h.session.iloc[-1], costs=h.costs.sum(),
                                           partial_year=year == int(result["ledger"].session.iloc[-1][:4]) and result["status"].startswith("failed")))
            print(case, name, result["status"], row["stop_date"], round(row["terminal_equity"], 2), flush=True)
    summary = pd.DataFrame(summary)
    summary.to_csv(args.output/"summary.csv", index=False)
    pd.DataFrame(yearly).to_csv(args.output/"yearly_observed.csv", index=False)
    # The benchmark is two initially half-funded sleeves, not daily 50/50 remixing.
    half_ledgers = [pd.read_csv(args.output/"base"/name/"ledger.csv.gz").set_index("session") for name in ("trend_half", "carry_half")]
    common = half_ledgers[0].index.intersection(half_ledgers[1].index)
    aggregate = half_ledgers[0].loc[common, ["opening_equity", "equity", "positions", "stale_contracts"]]+half_ledgers[1].loc[common, ["opening_equity", "equity", "positions", "stale_contracts"]]
    aggregate = aggregate.reset_index()
    monthly["half_mix"] = monthly_account(aggregate, protocol, tape.dates)
    for name, frame in monthly.items():
        frame.to_csv(args.output/(name+"_monthly.csv"), index=False)
    inference = paired_inference(monthly, {"synthetic_demo":("2021-01", "2022-12")} if args.fixture else None)
    inference.to_csv(args.output/"paired_inference.csv", index=False)
    events = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame(columns=["session", "product", "code", "detail", "case", "strategy"])
    events.groupby(["case", "strategy", "code", "detail"]).size().rename("count").to_csv(args.output/"failure_counts.csv")
    figures(tape, base, summary[~summary.strategy.str.endswith("_half")], inference, args.output)
    nature = "PRIVATE LICENSED REAL REFERENCES" if manifest["data_kind"] == "restricted" else "SYNTHETIC DEMONSTRATION"
    table = summary[(summary["case"] == "base") & ~summary.strategy.str.endswith("_half")]
    report = ["# Commodity curves — "+nature, "", "Exploratory scheduled-calendar study; current-vintage inputs, proxy collateral and modeled fills. Not complete PIT or actual trading.", "",
              "## Fixed hypotheses and evidence", "", "Five rules, all predeclared costs/delays/sectors and both failed and completed paths are retained. The known FND/LTD boundary is not complete first-position history. Source rows outside the rule calendar remain in a separate exclusion artifact.", "",
              "## Base accounts", "", "|Strategy|Status|Last date|Observed ending USD|Costs USD|", "|---|---|---|---:|---:|"]
    for r in table.itertuples(index=False):
        report.append(f"|{r.strategy}|{r.status}|{r.stop_date}|{r.terminal_equity:,.2f}|{r.costs:,.2f}|")
    report += ["", "Ending values of failed paths cover different horizons and must not be ranked as full-period performance. Stale/incomplete months are ineligible for inference; they are not silently dropped.", "",
               "![Accounts and stopped paths](accounts_and_drawdowns.png)", "", "## Paired uncertainty", "", "The real protocol uses historical 2020–2025 confirmation, not unseen future data. The invented demonstration instead evaluates its entire synthetic 2021–2022 window and makes no validation claim. The benchmark sums separate $500k trend/carry account values, with each sleeve's own costs and integer quantities. Moving noncircular blocks use 6/12 months, 5,000 draws, seed 20261026; two-sided centered-null p-values and Holm family size two are retained.", "",
               "![Intervals or explicit non-evaluability](paired_uncertainty.png)", "", "## Funding and failures", "", "![Gross and proxy reserves](funding_constraints.png)", "", "![All predeclared scenarios](predeclared_sensitivities.png)", "",
               "## Contract coverage and curve mechanism", "", "![Qualified pairs](pair_coverage.png)", "", "![Fixed curve dates](curve_snapshots.png)", "",
               "## Interpretation and limits", "", "Carry measures a curve slope, trend a past near rolling return, and basis-momentum the difference between compounded near/far histories. Reference histories use the same contract at both endpoints, not a continuous-price jump. They are signal measurements, not proof of fills. Every scheduled interval must be present for a completed month.", "",
               "The rules calendar excludes declared holiday patterns, including Juneteenth from 2022. It does not reconstruct unexpected closures or original notices. Daily references may combine different source times; synchronous EOD booking is not an intraday funding simulation. The 10%/20% reserves are assumptions, without spread credits or broker add-ons. Fixed $2.50/side and outright ticks are modeled friction. No spot premium or convenience yield is independently identified.", "",
               "Later-decision scenarios postpone signal updates; they are not latency replays of an unchanged submitted order. Sector removals suppress those requests without reranking. All wealth paths retain continuous capital across periods. Integer rounding and rejected baskets can materially change results.", "",
               "## Reproduction and provenance", "", "See FROZEN_RUN.json, RUN_MANIFEST.json, summary.csv, paired_inference.csv, failure_counts.csv and each account's ledger/trades/RECEIPT.json. Base accounts also retain decisions, holdings and per-contract variation margin. Source rights remain those of the input manifest; restricted results are private."]
    (args.output/"REPORT.md").write_text("\n".join(report)+"\n", encoding="utf-8")
    receipt = dict(created_utc=datetime.now(timezone.utc).isoformat(), data_kind=manifest["data_kind"], elapsed_seconds=time.perf_counter()-started,
                   cases=len(cases), funded_paths=len(summary), completed_paths=int((~summary.status.str.startswith("failed")).sum()),
                   failed_paths=int(summary.status.str.startswith("failed").sum()), off_calendar_records=len(tape.off_calendar),
                   maximum_terminal_reconciliation_error=float(summary.reconciliation_error.abs().max()),
                   code=execution_code, package_version=__version__, python=sys.version, numpy=np.__version__, pandas=pd.__version__,
                   frozen_run_sha256=hashlib.sha256((args.output/"FROZEN_RUN.json").read_bytes()).hexdigest(),
                   files={f.relative_to(args.output).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.rglob("*") if f.is_file()})
    (args.output/"RUN_MANIFEST.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items() if k not in ("files", "code")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
