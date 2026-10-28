"""Controlled invented paired exit: capacity is relative to the initial unit.

This is an accounting/ordering experiment, not a selected trading strategy.
Run after installing the project, or with an independently installed wheel.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from strategy_lab import __version__
from strategy_lab.commodities.engine import PRODUCTS
from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol, run_research
from strategy_lab.commodities.research_fixture import research_frames

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
tape=prepare(*research_frames())
day=tape.dates.get_loc("2021-01-04")
j=PRODUCTS.index("WTI")
old=tape.pairs[day,j].copy()
third=tape.contracts.index[tape.contracts.contract.eq("SYN_RESEARCH_WTI_2")][0]
for score in tape.updates.values():
    score["bm_spread_near_direction"]=1  # fixed exogenous accounting-control requests
protocol=ResearchProtocol(start="2021-01-04",end="2021-01-15",execution_policy="staged")
initial=run_research(tape,"bm_spread",replace(protocol,end=protocol.start))
units=int(initial["holdings"].query("product == 'WTI'").quantity.abs().max())
far_capacity=max(1,units//3)
near_capacity=3*far_capacity
tape.pairs[day+1:day+30,j]=[old[1],third]
tape.volume[day-1:day+25,old[0]]=near_capacity/protocol.participation
tape.volume[day-1:day+25,old[1]]=far_capacity/protocol.participation
result=run_research(tape,"bm_spread",protocol)
plans=result["exit_plans"].query("product == 'WTI'").copy()
holdings=result["holdings"].query("product == 'WTI'")
dates=result["ledger"].session
trace=pd.DataFrame(dict(session=dates))
for slot,key in zip(("old_near","old_far","replacement_far"),[old[0],old[1],third]):
    values=holdings[holdings.contract==tape.contracts.contract.iloc[key]].set_index("session").quantity
    trace[slot]=trace.session.map(values).fillna(0).astype(int)
trace=trace.merge(plans[["session","planned_units","required_units"]],on="session",how="left",validate="one_to_one")
trace["old_pair_sum"]=trace.old_near+trace.old_far
assert trace[trace.replacement_far.eq(0)].old_pair_sum.eq(0).all()
trace.to_csv(args.output/"TRACE.csv",index=False)
result["trades"].query("product == 'WTI'").to_csv(args.output/"TRADES.csv",index=False)
plans.to_csv(args.output/"EXIT_PLANS.csv",index=False)
fig,axes=plt.subplots(2,1,figsize=(10,6.5),sharex=True,constrained_layout=True)
x=pd.to_datetime(trace.session)
axes[0].step(x,trace.old_near,where="post",label="Old near (+)",color="#101928")
axes[0].step(x,trace.old_far,where="post",label="Old far (-)",color="#36B3A8")
axes[0].step(x,trace.replacement_far,where="post",label="Replacement far",color="#B97B45",linestyle="--")
axes[0].set(ylabel="Signed contracts",title="Equal old-leg slices; replacement waits for retirement")
axes[0].legend(ncol=3)
axes[1].bar(x,trace.planned_units.fillna(0),label="Frozen paired reduction",color="#36B3A8")
axes[1].axhline(far_capacity,color="#B05754",linestyle="--",label="Binding far-leg allowance")
axes[1].set(ylabel="Paired units",xlabel="Scheduled decision / booking date")
axes[1].legend()
fig.suptitle("INVENTED CONTROL · staggered old-leg exit · not commodity performance")
fig.savefig(args.output/"paired_slices.png",dpi=160)
plt.close(fig)
report=f'''# Invented paired-retirement trace

This is a deliberately controlled accounting experiment. Requests use fixed
positive spread directions on original generated curves. They are not the
cross-sectional strategy results or market-calibrated order flow.

Initial WTI spread size is {units} paired units under the recorded risk rule.
The artificial near allowance is {near_capacity}, far allowance {far_capacity};
both are defined relative to that initial size to expose multi-day ordering.
The roll request changes the pair on the next session. No return objective is
used to set these capacities. The smaller old-leg allowance limits each slice.

![Paired slices](paired_slices.png)

TRACE.csv records actual day-end holdings; EXIT_PLANS.csv records frozen intent;
TRADES.csv records modeled fills and both side costs. Replacement orders wait
for the latched old goal; overlap consumes remaining daily capacity and can be
rejected even after the old basket has become flat. Later replacement holdings
are a different pair and are not added to the old-pair neutrality check.

No WRDS records or derived real findings are included. See the repository's
docs/COMMODITY_STAGED_EXITS.md for the separate early-retirement protocol.
'''
(args.output/"REPORT.md").write_text(report,encoding="utf-8")
receipt=dict(data_kind="synthetic",package_version=__version__,initial_units=units,
             near_capacity=near_capacity,far_capacity=far_capacity,
             provenance="Original invented fixture; controlled exogenous requests and quantity-relative activity, not strategy calibration",
             example_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             reconciliation=result["reconciliation"],
             files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.iterdir() if f.is_file()})
(args.output/"RECEIPT.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in receipt.items() if k!="files"},indent=2))
