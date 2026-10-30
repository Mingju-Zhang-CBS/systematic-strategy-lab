from pathlib import Path
from dataclasses import replace, asdict
import argparse
import hashlib
import json
import platform
from importlib.resources import files
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from .engine import Config, backtest
from .demo import fixture


def run(bars, quotes, output, data_kind):
    out=Path(output); out.mkdir(parents=True,exist_ok=True)
    summary=[]
    plt.rcParams.update({'figure.facecolor':'#FAF9F5','axes.facecolor':'#FAF9F5',
                         'axes.spines.top':False,'axes.spines.right':False,
                         'axes.prop_cycle':plt.cycler(color=['#101928','#36B3A8','#B86E45','#6B9E8B','#756B91','#A17C5E'])})
    fig, ax=plt.subplots(figsize=(10,5),layout="constrained")
    for variant in ["base","vwap","vol_scaled"]:
        for delay in [1,60]:
            config=replace(Config(), delay_seconds=delay)
            daily, orders, features=backtest(bars,quotes,variant,config)
            folder=out/f"{variant}-{delay}s";folder.mkdir(exist_ok=True)
            daily.to_csv(folder/"daily.csv",index=False);orders.to_csv(folder/"orders.csv",index=False)
            features.to_csv(folder/"features.csv",index=False)
            if daily.empty:
                summary.append({"variant":variant,"delay_seconds":delay,"status":"insufficient_history"})
                continue
            equity=np.r_[config.initial_cash,daily.equity]
            summary.append({"variant":variant,"delay_seconds":delay,"sessions":len(daily),
                            "status":daily.status.iloc[-1],"net_pnl_usd":equity[-1]-equity[0],
                            "max_drawdown":float(np.min(equity/np.maximum.accumulate(equity)-1)),
                            "missing_quotes":int(daily.missing_quotes.sum()),
                            "financing_borrow":float((daily.financing+daily.borrow).sum())})
            ax.plot(pd.to_datetime(daily.session),daily.equity,label=f"{variant} / {delay}s")
    ax.set(title=f"{data_kind}: signal first, quote later",ylabel="Account equity (USD)",xlabel="Session")
    locator=mdates.AutoDateLocator(minticks=4,maxticks=6)
    ax.xaxis.set_major_locator(locator);ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.legend(ncol=2);fig.savefig(out/"execution.png",dpi=160);plt.close(fig)
    table=pd.DataFrame(summary);table.to_csv(out/"summary.csv",index=False)
    (out/"REPORT.md").write_text("# Intraday Execution Study\n\nData kind: **"+data_kind+"**.\n\n"
        "![Execution](execution.png)\n\n```csv\n"+table.round(6).to_csv(index=False)+"```\n\n"
        "The offline fixture is invented and is not performance evidence. Quote models cross the observed bid/ask "
        "after the decision plus the declared latency; they do not demonstrate actual routing or queue priority. "
        "Missing exit quotes retain inventory and stop the account; remaining equity is provisional. "
        "Initial margin, fees, slippage, financing, borrow availability and participation are declared proxies. "
        "A higher scaled return does not isolate a stronger signal. Historical licensed results remain private.\n",encoding="utf-8")
    (out/"run.json").write_text(json.dumps({"generated_utc":datetime.now(timezone.utc).isoformat(),
        "data_kind":data_kind,"machine":platform.platform(),"config":asdict(Config()),
        "protocol_sha256":hashlib.sha256(files('strategy_lab').joinpath('data/intraday_protocol.json').read_bytes()).hexdigest(),
        "source_sha256":{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()
                          for n in ['engine.py','demo.py','__main__.py']},
        "bars_sha256":hashlib.sha256(bars.to_csv(index=False).encode()).hexdigest(),
        "quotes_sha256":hashlib.sha256(quotes.to_csv(index=False).encode()).hexdigest()},indent=2))
    return table


def main():
    p=argparse.ArgumentParser(description="Offline intraday research; never submits orders")
    p.add_argument("--demo",action="store_true");p.add_argument("--bars",type=Path);p.add_argument("--quotes",type=Path)
    p.add_argument("--output",type=Path,default=Path("output/intraday"));a=p.parse_args()
    if a.demo and a.bars is None and a.quotes is None:
        b,q=fixture();kind="synthetic"
    elif not a.demo and a.bars is not None and a.quotes is not None:
        b,q=pd.read_csv(a.bars),pd.read_csv(a.quotes);kind="user-supplied-private"
    else:
        p.error("Choose --demo OR both --bars and --quotes")
    print(run(b,q,a.output,kind).to_string(index=False))


if __name__=="__main__":main()
