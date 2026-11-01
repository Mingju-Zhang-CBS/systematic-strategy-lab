"""Generate all fixed scenarios; retain failed training and unfavorable outcomes."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from .config import RegimeConfig, SEGMENTS, STRATEGIES
from .data import ASSETS, synthetic_prices, validate_prices
from .models import features, online_states, steady_gain
from .engine import targets, backtest, metrics, paired_interval
from ..runtime import require_empty_output


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def write_csv(path, frame):
    frame.to_csv(path, index=False, float_format="%.17g", lineterminator="\n")


def protocol(cfg):
    return {"protocol_version": "regimes-v1", "config": asdict(cfg), "assets": list(ASSETS),
            "segments": SEGMENTS, "strategies": list(STRATEGIES), "cost_bps": [0, 5, 10],
            "annual_continuous_cash_rates": [0., .03], "bootstrap_blocks": [20, 63],
            "ema_steady_gain": steady_gain(cfg.process_variance, cfg.measurement_variance),
            "hmm_covariance": "diag", "hmm_min_covar": 1e-4,
            "execution": "signal after close t; frozen target fraction at close t+1",
            "market_units": "adjusted-close total-return model units, not ETF shares",
            "gate": "kalman momentum > 0 AND filtered weighted current-state log-return mean > 0",
            "failure_policy": "request cash until next scheduled refit; fill one session later",
            "evidence": "retrospective current-vintage experiment, no prospective or PIT claim"}


def run_study(frame, output, cfg=RegimeConfig(), data_kind="synthetic", source=None, input_hash=None):
    cfg.validate()
    d = validate_prices(frame)
    if data_kind not in {"synthetic", "private-real-current-vintage"}:
        raise ValueError("Explicit known data kind required")
    out = require_empty_output(output)
    write_json(out/"protocol.json", protocol(cfg))
    if input_hash is None:
        input_hash = hashlib.sha256(d.to_csv(index=False, float_format="%.17g", lineterminator="\n").encode()).hexdigest()
    records = []; paired = []; diagnostics = []; base_ledgers = {}
    for asset in ASSETS:
        print(f"{data_kind}: fitting {asset} online states", flush=True)
        prices = d[d.ticker.eq(asset)].set_index("date").adjusted_close
        f = features(prices, cfg)
        states, fits, snapshots = online_states(f, "2013-01-01", cfg)
        weights = targets(f, states, cfg)
        asset_out = out/asset; asset_out.mkdir()
        write_csv(asset_out/"features.csv", f.reset_index())
        write_csv(asset_out/"state_probabilities.csv", states)
        write_csv(asset_out/"training_events.csv", fits)
        write_json(asset_out/"model_snapshots.json", snapshots)
        write_csv(asset_out/"targets.csv", weights.reset_index())
        for segment, (lo, hi) in SEGMENTS.items():
            state_slice = states[(states.date >= lo) & (states.date <= hi)]
            fit_slice = fits[(fits.decision_date >= lo) & (fits.decision_date <= hi)]
            diagnostics.append({"asset": asset, "segment": segment,
                                "observations": len(state_slice), "refits": len(fit_slice),
                                "failed_refits": int(fit_slice.status.ne("ok").sum()),
                                "cash_request_days": int(state_slice.status.ne("ok").sum())})
        for bps in (0, 5, 10):
            for rate in (0., .03):
                case = f"cost-{bps:02d}_cash-{int(rate*100):02d}"
                case_out = asset_out/case; case_out.mkdir()
                ledgers = {}
                for strategy in STRATEGIES:
                    ledger, decisions, trades = backtest(prices.loc[weights.index], weights[strategy], cfg,
                                                         strategy, bps, rate)
                    ledgers[strategy] = ledger
                    write_csv(case_out/f"{strategy}_ledger.csv", ledger)
                    write_csv(case_out/f"{strategy}_decisions.csv", decisions)
                    write_csv(case_out/f"{strategy}_trades.csv", trades)
                    for segment, (lo, hi) in SEGMENTS.items():
                        selection = ledger[ledger.date.between(lo, hi)]
                        if selection.empty:
                            raise ValueError(f"Missing evaluation segment {segment}")
                        records.append({"asset": asset, "segment": segment, "strategy": strategy,
                                        "cost_bps": bps, "cash_rate": rate, **metrics(selection)})
                for segment, (lo, hi) in SEGMENTS.items():
                    a = ledgers["kalman_hmm"]; b = ledgers["kalman_momentum"]
                    selection = a.date.between(lo, hi)
                    difference = (a.loc[selection, "return"]-b.loc[selection, "return"]).to_numpy()
                    exposure = a.loc[selection, "held_weight"].mean()-b.loc[selection, "held_weight"].mean()
                    for block in (20, 63):
                        paired.append({"asset": asset, "segment": segment, "cost_bps": bps,
                                       "cash_rate": rate, "average_exposure_difference": float(exposure),
                                       **paired_interval(difference, block, cfg.bootstrap_samples, cfg.seed)})
                if bps == 5 and rate == 0:
                    base_ledgers[asset] = ledgers
    summary = pd.DataFrame(records); inference = pd.DataFrame(paired); diagnostics = pd.DataFrame(diagnostics)
    write_csv(out/"metrics.csv", summary)
    write_csv(out/"paired_inference.csv", inference)
    write_csv(out/"training_summary.csv", diagnostics)
    plot_results(base_ledgers, inference, out, data_kind)
    write_report(summary, inference, diagnostics, out, data_kind)
    root = Path(__file__).resolve().parent
    versions = {name: importlib.metadata.version(name) for name in
                ("numpy", "pandas", "scipy", "scikit-learn", "hmmlearn", "joblib", "threadpoolctl", "matplotlib")}
    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(), "data_kind": data_kind,
                "input_sha256": input_hash, "protocol_sha256": sha256(out/"protocol.json"),
                "source": source or {"origin": "independently generated invented business-day fixture"},
                "source_sha256": {p.name: sha256(p) for p in sorted(root.glob("*.py"))},
                "python": platform.python_version(), "packages": versions,
                "artifacts": {p.relative_to(out).as_posix(): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}}
    write_json(out/"manifest.json", manifest)
    print(f"Completed {len(summary)} metric rows and {len(inference)} paired intervals", flush=True)
    return summary, inference, diagnostics


def plot_results(ledgers, inference, out, kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": "#f5f1e9", "axes.facecolor": "#f5f1e9",
                         "text.color": "#101928", "axes.labelcolor": "#101928", "font.size": 10})
    colors = ("#101928", "#83919e", "#bd7950", "#826899", "#4274a0", "#22998f")
    label = "SYNTHETIC — invented inputs" if kind == "synthetic" else "PRIVATE — current-vintage Yahoo reference"
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    for ax, asset in zip(axes, ASSETS):
        for strategy, color in zip(STRATEGIES, colors):
            frame = ledgers[asset][strategy]
            ax.plot(pd.to_datetime(frame.date), frame.nav/100000, label=strategy.replace("_", " "), color=color, lw=1.3)
        ax.set_title(f"{asset} model accounts | 5 bp per traded dollar; 0% cash")
        ax.set_ylabel("Model wealth / initial wealth"); ax.grid(alpha=.2)
    axes[0].legend(ncol=3, fontsize=8)
    fig.suptitle(label+"\nCausal trend comparison; no actual ETF fills", fontsize=13)
    fig.savefig(out/"wealth.png", dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    selected = inference[(inference.cost_bps == 5) & (inference.cash_rate == 0) & (inference.block_sessions == 20)]
    for ax, asset in zip(axes, ASSETS):
        rows = selected[selected.asset.eq(asset) & ~selected.segment.eq("full")]
        for i, row in enumerate(rows.itertuples()):
            ax.plot([row.lower_95*100, row.upper_95*100], [i, i], color="#22998f", lw=3)
            ax.scatter(row.annualized_mean_difference*100, i, color="#101928", zorder=3)
        ax.axvline(0, color="#83919e", ls="--")
        ax.set_yticks(range(len(rows)), rows.segment); ax.set_title(asset)
        ax.set_xlabel("HMM minus Kalman: annualized mean (percentage points)")
        ax.grid(axis="x", alpha=.2)
    fig.suptitle(label+"\nPaired 95% moving-block intervals, 20-session blocks", fontsize=12)
    fig.savefig(out/"paired_intervals.png", dpi=160); plt.close(fig)


def write_report(summary, inference, diagnostics, out, kind):
    label = "SYNTHETIC / INVENTED INPUTS" if kind == "synthetic" else "PRIVATE / REAL CURRENT-VINTAGE REFERENCE"
    lines = [f"# Online regimes and daily trend — {label}", "",
             "Does an online HMM add value beyond smoothing and volatility control?", "",
             "These are retrospective model total-return-unit accounts, not ETF fills. "
             "The synthetic run cannot establish market alpha; current-vintage real data cannot establish historical PIT availability.", "",
             "## Fixed comparison", "",
             "SPY is primary; QQQ is a transfer check. Decisions follow the close and execute at the next session close. "
             "All six methods share evaluation dates; positions continue across segment boundaries. "
             "Buy-and-hold trades once; other methods rebalance daily to frozen fractions. "
             "Cost is charged on actual drifted-unit trades. No dividend is added to adjusted prices.", "",
             "## Confirmation window: 2021–2025", "",
             "Base scenario: 5 bp per traded dollar; cash earns 0%.", "",
             "| Asset | Method | CAGR | Excess Sharpe | Max drawdown | Average held exposure | Annual turnover |",
             "|---|---|---:|---:|---:|---:|---:|"]
    selected = summary[(summary.segment == "confirmation") & (summary.cost_bps == 5) & (summary.cash_rate == 0)]
    for r in selected.itertuples():
        sharpe = "undefined" if pd.isna(r.excess_sharpe) else f"{r.excess_sharpe:.2f}"
        lines.append(f"| {r.asset} | {r.strategy} | {r.cagr:.2%} | {sharpe} | {r.max_drawdown:.2%} | {r.average_held_weight:.1%} | {r.annualized_turnover:.2f}x |")
    lines += ["", "![Model wealth](wealth.png)", "", "## Incremental HMM evidence", "",
              "| Asset | Block sessions | Annualized paired mean | 95% interval | Exposure difference |",
              "|---|---:|---:|---:|---:|"]
    selected = inference[(inference.segment == "confirmation") & (inference.cost_bps == 5) & (inference.cash_rate == 0)]
    for r in selected.itertuples():
        lines.append(f"| {r.asset} | {r.block_sessions} | {r.annualized_mean_difference:.2%} | [{r.lower_95:.2%}, {r.upper_95:.2%}] | {r.average_exposure_difference:.1%} |")
    lines += [""]
    for asset in ASSETS:
        rows = selected[selected.asset.eq(asset)]
        estimate = rows.annualized_mean_difference.iloc[0]
        direction = "positive" if estimate > 0 else "negative" if estimate < 0 else "zero"
        crosses = ((rows.lower_95 <= 0) & (rows.upper_95 >= 0)).all()
        uncertainty = "Both block-length intervals include zero." if crosses else "Inspect both block lengths; exclusion of zero is not a prospective alpha result."
        lines.append(f"{asset}: the fixed base-case confirmation point estimate is {direction}. {uncertainty} "
                     "Compare the exposure difference before attributing the result to predictive information.")
    lines += ["", "The statistic is 252 times the paired daily arithmetic-return mean, not a CAGR difference. "
              "The intervals are descriptive, dependent-data diagnostics without multiplicity adjustment. "
              "A change in exposure is part of the rule; these comparisons do not isolate predictive information from de-risking.", "",
              "![Paired intervals](paired_intervals.png)", "", "## Training failures retained", "",
              "| Asset | Refits | Failed refits | Days requesting cash |", "|---|---:|---:|---:|"]
    for r in diagnostics[diagnostics.segment.eq("full")].itertuples():
        lines.append(f"| {r.asset} | {r.refits} | {r.failed_refits} | {r.cash_request_days} |")
    lines += ["", "## Every confirmation sensitivity", "",
              "20-session-block paired intervals; 63-session results are also retained in the CSV.", "",
              "| Asset | Cost bp | Cash assumption | HMM minus Kalman annualized mean | 95% interval |",
              "|---|---:|---:|---:|---:|"]
    cases = inference[(inference.segment == "confirmation") & (inference.block_sessions == 20)]
    for r in cases.itertuples():
        lines.append(f"| {r.asset} | {r.cost_bps} | {r.cash_rate:.0%} | {r.annualized_mean_difference:.2%} | [{r.lower_95:.2%}, {r.upper_95:.2%}] |")
    lines += ["", "Failed models request cash until the next scheduled refit. The request takes one session to execute; "
              "failure counts are not evidence of trading success. Every failure reason and successful parameter snapshot is retained.", "",
              "## Complete evidence and limits", "",
              "`metrics.csv` preserves every asset × method × segment × cost (0/5/10 bp) × cash (0/3%) case. "
              "`paired_inference.csv` retains 20/63-session intervals for every case. "
              "Asset subfolders contain features, targets, model snapshots, state probabilities, training events, decisions, trades and cash/unit ledgers. "
              "`protocol.json` and `manifest.json` bind configuration, code, input and output fingerprints.", "",
              "Sharpe uses arithmetic excess daily returns. Cash accrues continuously over calendar days; "
              "0% and 3% are assumptions, not observed investment rates. Risk scaling is capped at 100% and need not attain 15% realized volatility. "
              "Model units do not establish executable adjusted prices, liquidity, taxes, or corporate-action release availability. "
              "Fixed Kalman gains approach the matched EMA: their similarity is expected, not independent confirmation. "
              "QQQ shares substantial equity exposure with SPY and is not an independent market. "
              "No parameters are chosen by confirmation performance; no positive result is required.", ""]
    (out/"REPORT.md").write_text("\n".join(lines), encoding="utf-8")
