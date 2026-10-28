"""Invented admission cases using the exact engine rule, without market data."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from strategy_lab import __version__
from strategy_lab.commodities.research import _entry_budget

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,required=True)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
cases=[("Room for exit",False,0,4,[2],30),
       ("Near the boundary",False,0,4,[2],5),
       ("Weak spread leg",True,0,20,[8,1],15),
       ("Increase 10 to 14",False,10,14,[1],13),
       ("Exact drain boundary",True,0,22,[2,5],13),
       ("Paired budget passes",True,0,6,[2,4],30),
       ("Zero weaker-leg capacity",True,0,2,[10,0],30)]
rows=[]
for name,paired,current,target,leg_capacities,remaining in cases:
    rows.append(dict(case=name,paired=paired,current_units=current,
                     leg_capacities=";".join(map(str,leg_capacities)),
                     **_entry_budget(target,min(leg_capacities),remaining,10,2)))
table=pd.DataFrame(rows)
table.to_csv(args.output/"CASES.csv",index=False)
fig,ax=plt.subplots(figsize=(11,6.5),constrained_layout=True)
colors=["#36B3A8" if admitted else "#B05754" for admitted in table.admitted]
ax.barh(table["case"],table.remaining_exit_sessions,color=colors,label="Available sessions after entry")
for i,row in enumerate(table.itertuples(index=False)):
    if row.required_drain_sessions is not None and pd.notna(row.required_drain_sessions):
        threshold=max(10,row.required_drain_sessions+2)
        ax.plot(threshold,i,"kx",markersize=9,label="Must strictly exceed this threshold" if i==0 else None)
    else:
        ax.text(1,i,"No exit-capacity budget",va="center",color="white")
ax.invert_yaxis()
ax.set(xlabel="Scheduled exit sessions; entry day is excluded",title="INVENTED CASES · total exposure and weaker leg govern admission",xlim=(0,40))
ax.legend(loc="lower right",fontsize=8)
fig.savefig(args.output/"admission_cases.png",dpi=160)
plt.close(fig)
report='''# Invented entry / exit budget cases

These seven inputs are deliberately constructed accounting/risk cases. They use
no WRDS records, observed trading outcomes or market-calibrated fill estimates.
The exact helper used by the research engine produces CASES.csv.

![Admission cases](admission_cases.png)

Green means the fixed budget passes; red means the addition is refused. A pass
is not a fill. Pending exits, quotes/activity, shared side capacity and funding
remain separate execution checks. The black marker is an excluded boundary:
available sessions must strictly exceed both ten and projected drainage plus two.

The increase from ten to fourteen units is tested on fourteen, not the increment
four. For a spread, the weaker leg's allowance and earliest deadline govern the
whole paired request. Zero capacity has no finite drain budget. Entry day cannot
be credited as a future retirement day because it books at the EOD reference.

See docs/COMMODITY_ADMISSION.md and tests/test_commodity_entry_budget.py in the
repository for the complete protocol and executable invariants. This diagram is
not a trading-performance result or evidence of future liquidity.
'''
(args.output/"REPORT.md").write_text(report,encoding="utf-8")
receipt=dict(data_kind="synthetic",package_version=__version__,cases=len(table),
             admitted=int(table.admitted.sum()),refused=int((~table.admitted).sum()),
             provenance="Original invented unit/time/capacity cases; no market records or real derived findings",
             example_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.iterdir() if f.is_file()})
(args.output/"RECEIPT.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in receipt.items() if k!="files"},indent=2))
