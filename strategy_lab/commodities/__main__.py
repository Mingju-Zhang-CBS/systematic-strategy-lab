"""Reproduce stage-2 fixtures or evaluate a private standardized input bundle."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .engine import Protocol, run, validate
from .fixture import frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", action="store_true")
    source.add_argument("--input", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = Protocol(**json.loads(args.protocol.read_text(encoding="utf-8"))) if args.protocol else Protocol()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output must be new or empty; preserve previous run evidence")
    if args.fixture:
        values = frames()
    else:
        manifest = json.loads((args.input / "manifest.json").read_text(encoding="utf-8"))
        values = (pd.read_csv(args.input / "quotes.csv"), pd.read_csv(args.input / "contracts.csv"),
                  pd.read_csv(args.input / "calendar.csv"), manifest, manifest["start"], manifest["end"])
    data = validate(*values, protocol)
    result = run(data, protocol)
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("ledger", "trades", "decisions", "selections", "events", "holdings"):
        result[name].to_csv(args.output / f"{name}.csv", index=False, lineterminator="\n")
    ledger, trades, events = result["ledger"], result["trades"], result["events"]
    label = data.manifest["data_kind"].upper()
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                         "figure.facecolor": "#faf9f5", "axes.facecolor": "#faf9f5", "text.color": "#101928"})
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    if not ledger.empty:
        x = pd.to_datetime(ledger["session"])
        axes[0].plot(x, ledger["equity"] - protocol.capital, color="#101928", label="Net marked P&L")
        axes[0].plot(x, ledger["variation_margin"].cumsum(), color="#36B3A8", label="Cumulative variation margin")
        axes[0].set_ylabel("USD; modeled marks")
        axes[0].legend(loc="best")
        axes[1].plot(x, ledger["reserve"] / ledger["equity"], color="#36B3A8", label="Model reserve / equity")
        axes[1].axhline(protocol.reserve_limit, ls="--", color="#a44", label="Reserve ceiling")
        axes[1].set_ylabel("Fraction of equity")
        axes[1].legend(loc="best")
        axes[2].step(x, ledger["costs"].cumsum(), color="#101928", label="Cumulative friction")
        axes[2].set_ylabel("USD; all legs")
        axes[2].legend(loc="best")
    fig.suptitle(f"{label} · Eight-product futures accounting diagnostic\nFixed one-contract near/far requests; not a signal performance study")
    fig.savefig(args.output / "accounting.png", dpi=160)
    plt.close(fig)
    metrics = dict(status=result["status"], data_kind=data.manifest["data_kind"],
                   sessions=len(ledger), products=int(data.contracts["product"].nunique()),
                   executed_legs=len(trades), event_counts=events["code"].value_counts().to_dict(),
                   ending_equity=None if ledger.empty else float(ledger.iloc[-1]["equity"]),
                   total_costs=0 if trades.empty else float(trades["total_cost"].sum()),
                   maximum_ledger_bridge_error=0 if ledger.empty else float((ledger["opening_equity"] + ledger["variation_margin"] - ledger["costs"] - ledger["equity"]).abs().max()),
                   strategy_alpha_evaluated=False, historical_tradability_certified=False)
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2)+"\n", encoding="utf-8", newline="\n")
    text = f"""# Futures accounting diagnostic — {label}

This is stage 2: contract qualification, fixed near/far requests and a funded ledger.
It is **not** a carry, momentum, basis-momentum or executable-alpha backtest.

- Status: `{result['status']}`.
- Products represented in the input: {metrics['products']}.
- Account dates recorded: {metrics['sessions']}; executed legs: {metrics['executed_legs']}.
- Total modeled costs: ${metrics['total_costs']:,.2f}.
- Maximum daily cash-bridge error: ${metrics['maximum_ledger_bridge_error']:.10f}.
- Data source: {data.manifest['source']}.
- Rights: {data.manifest['rights']}.

![Cash bridge, model collateral and costs](accounting.png)

Read `selections.csv` for every considered contract and exclusion; `decisions.csv`
for frozen quantities and observation/availability clocks; `trades.csv` for each
leg's reference price, commission and tick cost; `holdings.csv` for signed positions;
and `ledger.csv` for cash, provisional variation margin, encumbered reserves and
stale marks. `events.csv` retains rejected baskets and funding/safe-exit failures.

## Interpretation

The fixture tests a mechanism; synthetic dollar outcomes are not empirical evidence.
Each leg pays ${protocol.commission:.2f} commission plus {protocol.slippage_ticks:g}
outright ticks per side. Margin is a {protocol.reserve_rate:.0%} gross-based model
reserve without offsets, capped at {protocol.reserve_limit:.0%} of account equity;
it is not SPAN or a broker's historical requirement. Selection uses lagged activity;
the {protocol.participation:.0%} participation cap is a scenario, not measured fills.

Settlement is a retrospective marking reference. Cash timestamps do not reproduce
clearing intraday calls. Independent legs must all have a reference and modeled
capacity; an all-or-none basket is an idealization, not a guaranteed spread fill.
Negative settlements are permitted; no log or price-denominator return is used.
Full strategy inference and historical specification/calendar certification remain
separate acceptance gates. A future-known revision never changes an earlier target,
but current-vintage revisions can change this retrospective marked ledger.
"""
    (args.output / "REPORT.md").write_text(text, encoding="utf-8", newline="\n")
    if args.fixture:
        from .scenarios import write_scenarios
        scenarios = write_scenarios(args.output / "scenarios", protocol)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
        control = scenarios.iloc[:6]
        axes[0].barh(control.scenario, control.costs, color="#36B3A8")
        axes[0].set_xlabel("Modeled total leg costs (USD)")
        axes[0].set_title("Eight-product controls; all reported")
        faults = scenarios.iloc[6:]
        axes[1].barh(faults.scenario, faults.executed_legs, color="#101928")
        axes[1].set_xlabel("Executed legs before rejection / stop")
        axes[1].set_title("Single-product faults; not strategy returns")
        fig.suptitle("SYNTHETIC · Fixed controls and retained failures")
        fig.savefig(args.output / "controls-and-failures.png", dpi=160)
        plt.close(fig)
        with (args.output / "REPORT.md").open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n## Predeclared synthetic controls and failures\n\n")
            f.write("Every row below is reported. One-product faults deliberately have a different scope from the eight-product controls.\n\n")
            f.write("|Scenario|Products|Status|Executed legs|Costs (USD)|\n|---|---:|---|---:|---:|\n")
            for row in scenarios.itertuples(index=False):
                f.write(f"|{row.scenario}|{row.products}|{row.status}|{row.executed_legs}|{row.costs:,.2f}|\n")
            f.write("\nSee [scenario summary](scenarios/scenario-summary.csv) and each scenario's retained ledger and events. No failed path is discarded.\n")
            f.write("\n![Predetermined controls and failures](controls-and-failures.png)\n")
    inputs = {name: hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode()).hexdigest()
              for name, frame in zip(("quotes", "contracts", "calendar"), (data.quotes, data.contracts, data.calendar))}
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
    outputs = {p.relative_to(args.output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(args.output.rglob("*")) if p.is_file()}
    receipt = dict(created_utc=datetime.now(timezone.utc).isoformat(), protocol=asdict(protocol),
                   protocol_sha256=hashlib.sha256(json.dumps(asdict(protocol), sort_keys=True).encode()).hexdigest(),
                   manifest=data.manifest, input_sha256=inputs, code_sha256=code, output_sha256=outputs)
    (args.output / "run-manifest.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
