"""Compare fixed-world exit/cash diagnostics, never a return-selected winner."""
import argparse
import hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--protected',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    manifests=[json.loads((d/'RUN_MANIFEST.json').read_text(encoding='utf-8')) for d in [args.baseline,args.protected]]
    if manifests[0]['data_kind']!=manifests[1]['data_kind']:
        raise ValueError('comparison inputs must have the same rights/data category')
    for name in ['FROZEN_COHORTS.csv','FROZEN_LEGS.csv']:
        if (args.baseline/name).read_bytes()!=(args.protected/name).read_bytes():
            raise ValueError('comparison requires identical original event dates, signs and anchors')
    a=pd.read_csv(args.baseline/'summary.csv');b=pd.read_csv(args.protected/'summary.csv')
    keys=['stress_case','account_case','strategy']
    result=a.merge(b,on=keys,suffixes=('_baseline','_protected'),validate='one_to_one',how='outer',indicator=True)
    if len(result)!=72 or not result['_merge'].eq('both').all():
        raise ValueError('all nine scenarios and eight accounts must be retained')
    keep=keys+[v+suffix for v in ['status','stop_date','sessions','exposed_sessions','executed_legs','minimum_free_cash','max_cash_shortfall'] for suffix in ['_baseline','_protected']]
    args.output.mkdir(parents=True,exist_ok=False)
    result[keep].to_csv(args.output/'policy_comparison.csv',index=False)
    cases=a.stress_case.drop_duplicates().tolist()
    fig,axes=plt.subplots(1,2,figsize=(15,7),constrained_layout=True)
    for i,(frame,label,color) in enumerate([(a,'Original','#b05754'),(b,'Joint buffer','#36b3a8')]):
        complete=[int(frame[frame.stress_case.eq(c)].status.str.startswith('completed').sum()) for c in cases]
        axes[0].barh(np.arange(len(cases))+(i-.5)*.34,complete,height=.32,label=label,color=color)
    axes[0].set(yticks=range(len(cases)),yticklabels=cases,xlabel='Completed accounts out of eight; all stops retained',title='Completion is a feasibility diagnostic')
    axes[0].legend()
    names=[(r.account_case,r.strategy) for r in a[a.stress_case.eq('control')].itertuples(index=False)]
    for i,(folder,label,color) in enumerate([(args.baseline,'Original','#b05754'),(args.protected,'Joint buffer','#36b3a8')]):
        means=[]
        for account,strategy in names:
            ledger=pd.read_csv(folder/'control'/account/strategy/'ledger.csv.gz')
            reference=a[a.stress_case.eq('control')&a.account_case.eq(account)&a.strategy.eq(strategy)].iloc[0]
            assert len(ledger)==reference.sessions
            means.append(float(ledger.gross_proxy.mean()/reference.initial_capital))
        axes[1].barh(np.arange(len(names))+(i-.5)*.34,means,height=.32,label=label,color=color)
    axes[1].set(yticks=range(len(names)),yticklabels=[f'{x}/{y}' for x,y in names],xlabel='Mean gross proxy / starting capital; common complete controls',title='Inspect risk intensity and forgone exposure')
    nature='INVENTED INPUTS' if manifests[0]['data_kind']=='synthetic' else 'PRIVATE licensed references'
    fig.suptitle(nature+' · identical frozen worlds; no performance ranking',fontsize=12)
    fig.savefig(args.output/'policy_comparison.png',dpi=160);plt.close(fig)
    receipt=dict(data_kind=manifests[0]['data_kind'],rows=72,scope='All fixed scenarios; means use complete controls only; no return comparison',
        baseline_manifest_sha256=hashlib.sha256((args.baseline/'RUN_MANIFEST.json').read_bytes()).hexdigest(),
        protected_manifest_sha256=hashlib.sha256((args.protected/'RUN_MANIFEST.json').read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        outputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.iterdir() if f.is_file()})
    (args.output/'COMPARISON_RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'outputs'}},indent=2))


if __name__=='__main__':main()
