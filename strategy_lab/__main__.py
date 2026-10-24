from __future__ import annotations
import argparse,hashlib
from dataclasses import asdict,replace
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .core import Config,backtest,metrics,synthetic_market,validate_market
from .runtime import Measurement,manifest,dump,require_empty_output


def run(output,csv_path=None):
    out=require_empty_output(output);config=Config()
    data=validate_market(pd.read_csv(csv_path) if csv_path else synthetic_market())
    kind="user_supplied" if csv_path else "synthetic"
    data_hash=hashlib.sha256(data.to_csv(index=False,float_format="%.17g").encode()).hexdigest()
    runs={};sensitivity=[]
    with Measurement() as measured:
        for mode in ["momentum","static","spy","qqq"]:
            ledger,decisions,orders=backtest(data,config,mode)
            runs[mode]=metrics(ledger)
            (out/mode).mkdir()
            ledger.to_csv(out/mode/"ledger.csv",index=False)
            decisions.to_csv(out/mode/"decisions.csv",index=False)
            orders.to_csv(out/mode/"orders.csv",index=False)
        for delay in [1,2]:
            for bps in [0.,3.,10.]:
                ledger,_,_=backtest(data,replace(config,execution_delay=delay,cost_bps=bps))
                sensitivity.append({"delay_sessions":delay,"cost_bps":bps,**metrics(ledger)})
    dump(out/"metrics.json",{"data_kind":kind,"strategies":runs,"sensitivity":sensitivity,"measurement":measured.result})
    dump(out/"manifest.json",manifest(asdict(config),data_hash,kind))
    pd.DataFrame(sensitivity).to_csv(out/"sensitivity.csv",index=False)
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True,layout="constrained")
    for mode in runs:
        d=pd.read_csv(out/mode/"ledger.csv",parse_dates=["date"])
        wealth=np.r_[config.initial_nav,d.nav.to_numpy()]
        dd=(wealth/np.maximum.accumulate(wealth)-1)[1:]
        axes[0].plot(d.date,d.nav/config.initial_nav,label=mode)
        axes[1].plot(d.date,dd*100,label=mode)
    axes[0].set(ylabel="NAV / initial capital",title=f"{kind.title()} market: costs, cash and dividend receivables included")
    axes[1].set(ylabel="Drawdown (%)",xlabel="Synthetic session date" if kind=="synthetic" else "Session date")
    for ax in axes:ax.legend(ncol=4);ax.grid(alpha=.2)
    fig.savefig(out/"performance.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    tab=pd.DataFrame(sensitivity)
    for delay,g in tab.groupby("delay_sessions"):ax.plot(g.cost_bps,g.total_return*100,"o-",label=f"Delay {delay} session(s)")
    ax.set(xlabel="One-way proportional trading cost (bps)",ylabel="Total account return (%)",title="Fixed-rule sensitivity; same synthetic market" if kind=="synthetic" else "Fixed-rule sensitivity")
    ax.legend();ax.grid(alpha=.2);fig.savefig(out/"cost_delay.png",dpi=160);plt.close(fig)
    table="\n".join(f"|{mode}|{m['total_return']:.2%}|{m['excess_sharpe']:.3f}|{m['max_drawdown']:.2%}|{m['total_cost']:.2f}|" if m['excess_sharpe'] is not None else f"|{mode}|{m['total_return']:.2%}|undefined|{m['max_drawdown']:.2%}|{m['total_cost']:.2f}|" for mode,m in runs.items())
    (out/"REPORT.md").write_text(f"""# Fixed-rule allocation experiment

Data kind: **{kind}**. {'Ticker labels represent simulated roles; these are not actual ETF histories.' if kind=='synthetic' else 'Data were supplied by the user; this output is excluded from the public demo release.'}

|Strategy|Total return|Excess Sharpe|Maximum drawdown|Total trading costs|
|---|---:|---:|---:|---:|
{table}

![Account performance](performance.png)

![Cost and delay sensitivity](cost_delay.png)

## Economic conventions

The signal compares total-return indices over observations t-252 through t-21. At the first eligible close and subsequent month ends, positive-momentum assets receive equal target weights, capped at 50% each and 99% gross. A trailing 126-observation covariance scales risk down toward a 10% annual volatility budget. These are target limits at decision time; subsequent market moves can change realized weights. Static allocation uses equal weights without volatility scaling. SPY and QQQ controls enter once and then hold.

Weights are frozen at the decision close and executed at a later close. Integer quantities use the NAV and prices observed at execution; sales precede cash-constrained purchases. Costs apply to both purchases and sales. Cash earns the previous observed annual rate over actual elapsed days. Dividends accrue on the ex-date into receivables, become available after 20 supplied sessions, and are not spent or invested before payment. Split multipliers are new shares per old share; dividends are per post-split share. All strategies share the warmup and evaluation dates. Return statistics annualize at 252 observations; gross turnover is traded notional/NAV, not half that value.

## Checks and limitations

Every row reconciles ending NAV to prior NAV, stock price P&L, dividend entitlement, cash interest and fees. Selling and buying are modeled at daily closing prices; the example does not establish available liquidity, fills or capacity. Volume is validated but not used to claim participation limits. Dividend payment dates are an explicit model assumption. Signal thresholds and sensitivity scenarios are fixed; no best row is promoted. Historical user-data results are exploratory when those data have previously been inspected. This synthetic demonstration establishes accounting behavior, not alpha or an independent out-of-sample result.

See `manifest.json`, `metrics.json` and the per-strategy ledgers for configuration, source binding and measured resources.
""",encoding="utf-8")
    print(f"Strategy demo complete: data={kind}; four strategies and six sensitivity scenarios.")


def main():
    p=argparse.ArgumentParser(description="Offline multi-asset account simulation")
    p.add_argument("--csv",help="User-supplied long-form OHLC/dividend CSV; never bundled")
    p.add_argument("--real",action="store_true",help="Run the frozen real TSP NAV allocation study, entirely offline")
    p.add_argument("--output",default="local-runs/demo")
    a=p.parse_args()
    if a.real:
        if a.csv:p.error("--real uses the packaged NAV snapshot; --csv is the separate legacy raw-price simulation")
        from .real_report import run_real
        run_real(a.output)
    else:
        run(a.output,a.csv)

if __name__=="__main__":main()
