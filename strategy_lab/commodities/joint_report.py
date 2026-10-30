"""Extended supply outages, adverse price steps and proxy collateral calls."""
import argparse
from dataclasses import replace
from datetime import datetime,timezone
import hashlib,json,time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from strategy_lab import __version__
from .panel import prepare
from .research import ResearchProtocol,run_research
from .research_fixture import research_frames
from .research_report import write_result,summarize
from .stress import entry_cohorts
from .stress_report import ACCOUNTS,control_diagnostics
from .joint_stress import CASES,anchor_legs,compile_joint_stress


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',action='store_true');mode.add_argument('--input',type=Path)
    parser.add_argument('--cohorts',type=Path);parser.add_argument('--legs',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.fixture and (args.cohorts is None or args.legs is None):
        parser.error('private experiments require frozen --cohorts and --legs')
    args.output.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    if args.fixture:
        q,c,manifest=research_frames();p=ResearchProtocol(start='2021-01-01',end='2022-12-31')
        supplied=None;supplied_legs=None
    else:
        q=pd.read_csv(args.input/'quotes.csv.gz');c=pd.read_csv(args.input/'contracts.csv')
        manifest=json.loads((args.input/'manifest.json').read_text())
        for name,digest in manifest['files'].items():
            if hashlib.sha256((args.input/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('private input fingerprint mismatch: '+name)
        supplied=pd.read_csv(args.cohorts);supplied_legs=pd.read_csv(args.legs);p=ResearchProtocol()
    p=replace(p,execution_policy='staged',exit_lead=10,entry_budget=True)
    code={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}
    freeze=dict(created_utc=datetime.now(timezone.utc).isoformat(),data_kind=manifest['data_kind'],source=manifest,
        code=code,cases=CASES,accounts=ACCOUNTS,protocol=p.__dict__,package_version=__version__,
        cohort_sha256=None if args.fixture else hashlib.sha256(args.cohorts.read_bytes()).hexdigest(),
        leg_sha256=None if args.fixture else hashlib.sha256(args.legs.read_bytes()).hexdigest(),
        policy='Historical directions, contract selection and unit-risk reference histories fixed; current shocked VM/quotes and lagged shocked price basis affect cash/funding.',
        price='Fixed baseline side and lagged USD anchor. Additive steps persist after outage end; missing quotes stay missing; no negative-price clipping.',
        interpretation='Account-specific adverse paths; no cross-strategy alpha/benchmark inference, no unseen OOS and no return-selected severity.')
    (args.output/'FROZEN_RUN.json').write_text(json.dumps(freeze,indent=2),encoding='utf-8')
    tape=prepare(q,c,manifest,liquidity_window=5,monotone_roll=True)
    summary=[];cohort_records=[];leg_records=[]
    for account_case,name in ACCOUNTS:
        config=replace(p,extra_delay=3 if account_case=='delay_plus_3' else 0,capital=500_000 if name.endswith('_half') else 1_000_000)
        strategy=name.removesuffix('_half');base=run_research(tape,strategy,config)
        cohorts=entry_cohorts(base['trades'],strategy=='bm_spread') if supplied is None else supplied[(supplied.account_case==account_case)&(supplied.account==name)].copy()
        legs=anchor_legs(tape,cohorts,base['trades'],strategy=='bm_spread') if supplied_legs is None else supplied_legs[(supplied_legs.account_case==account_case)&(supplied_legs.account==name)].copy()
        cohort_records.append(cohorts.assign(account_case=account_case,account=name));leg_records.append(legs.assign(account_case=account_case,account=name))
        for case in CASES:
            stress=None if case['name']=='control' else compile_joint_stress(tape,cohorts,legs,case)
            result=base if stress is None else run_research(tape,strategy,config,stress=stress)
            if stress is None:
                result['stress_budgets'],result['stress_sessions']=control_diagnostics(tape,result,config)
            folder=args.output/case['name']/account_case/name
            write_result(result,folder,detail=True)
            for table in ['stress_budgets','stress_sessions']:
                result[table].to_csv(folder/(table+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
            if stress is not None:
                stress.windows.to_csv(folder/'stress_windows.csv',index=False)
                stress.price_events.to_csv(folder/'price_events.csv',index=False)
            ledger=result['ledger'];sessions=result['stress_sessions'];budgets=result['stress_budgets']
            row=summarize(result,account_case)
            for key in ['annual_return','annual_volatility','net_sharpe','worst_5pct_daily_mean']:
                row.pop(key)
            flags=sorted(set(result['events'].loc[result['events'].code.str.startswith('failed'),'code']))
            row.update(stress_case=case['name'],account_case=account_case,strategy=name,all_failure_flags=';'.join(flags),
                minimum_equity=float(ledger.equity.min()),minimum_free_cash=float(ledger.free_cash.min()),
                worst_daily_vm=float(ledger.variation_margin.min()),max_cash_shortfall=float(sessions.collateral_shortfall.max()),
                risk_buffer_breach_days=int(sessions.risk_buffer_breach.sum()),zero_capacity_checks=int(budgets.no_projected_capacity.sum()),
                nonpositive_finite_slack_checks=int(budgets.budget_slack.le(0).sum()))
            summary.append(row)
            stop=ledger.session.iloc[-1];day=tape.dates.get_loc(stop)
            held=result['holdings'][result['holdings'].session.eq(stop)]
            snapshots=[]
            for h in held.itertuples(index=False):
                key=int(tape.contracts.index[tape.contracts.contract.eq(h.contract)][0])
                raw=np.floor(config.participation*tape.volume[day-2,key])
                allowance=raw if stress is None else min(np.floor(raw*stress.capacity_factor[day-2,key]),np.floor(raw*stress.capacity_factor[day,key]))
                used=result['trades'].loc[result['trades'].session.eq(stop)&result['trades'].contract.eq(h.contract),'delta'].abs().sum()
                snapshots.append(dict(session=stop,product=h.product,contract=h.contract,quantity=h.quantity,mark=h.mark,
                    base_reference=tape.prices[day,key],price_offset=h.mark-tape.prices[day,key],multiplier=h.multiplier,
                    hard_deadline=str(tape.dates[tape.deadlines[key]].date()),offered_full_day_capacity=allowance,
                    already_used_sides=used,remaining_capacity=allowance-used,
                    equity=ledger.equity.iloc[-1],reserve=ledger.reserve.iloc[-1],free_cash=ledger.free_cash.iloc[-1],
                    primary_status=result['status'],all_failure_flags=';'.join(flags)))
            pd.DataFrame(snapshots,columns=['session','product','contract','quantity','mark','base_reference','price_offset','multiplier','hard_deadline','offered_full_day_capacity','already_used_sides','remaining_capacity','equity','reserve','free_cash','primary_status','all_failure_flags']).to_csv(folder/'terminal_inventory.csv',index=False)
            print(case['name'],account_case,name,result['status'],stop,flush=True)
    pd.concat(cohort_records,ignore_index=True).to_csv(args.output/'FROZEN_COHORTS.csv',index=False)
    pd.concat(leg_records,ignore_index=True).to_csv(args.output/'FROZEN_LEGS.csv',index=False)
    summary=pd.DataFrame(summary);summary.to_csv(args.output/'summary.csv',index=False)
    plt.rcParams.update({'figure.facecolor':'#faf8f3','axes.facecolor':'#faf8f3','font.size':9})
    nature='INVENTED INPUTS' if args.fixture else 'PRIVATE references + hypothetical joint shocks'
    grid=summary.assign(account=summary.account_case+'/'+summary.strategy).pivot(index='stress_case',columns='account',values='status').reindex([x['name'] for x in CASES])
    complete=~grid.apply(lambda s:s.str.startswith('failed'))
    fig,ax=plt.subplots(figsize=(14,7),constrained_layout=True)
    ax.imshow(complete.to_numpy().astype(int),aspect='auto',vmin=0,vmax=1,cmap=matplotlib.colors.ListedColormap(['#b05754','#36b3a8']))
    ax.set(yticks=range(len(grid)),yticklabels=grid.index,xticks=range(len(grid.columns)),xticklabels=grid.columns,title=nature+' · unchanged stopping boundaries; no prefix-return ranking')
    ax.tick_params(axis='x',rotation=25)
    for i in range(len(grid)):
        for j in range(len(grid.columns)):
            status=grid.iloc[i,j]
            label='complete' if complete.iloc[i,j] else ('equity' if 'nonpositive' in status else 'exit' if 'boundary' in status else 'cash')
            ax.text(j,i,label,ha='center',va='center',fontsize=8)
    fig.savefig(args.output/'completion.png',dpi=160);plt.close(fig)
    cash=summary.assign(account=summary.account_case+'/'+summary.strategy,ratio=summary.minimum_free_cash/summary.initial_capital).pivot(index='stress_case',columns='account',values='ratio').reindex(grid.index)
    extent=max(1,float(np.abs(cash.to_numpy()).max()))
    fig,ax=plt.subplots(figsize=(14,7),constrained_layout=True)
    im=ax.imshow(cash,aspect='auto',cmap='RdBu',vmin=-extent,vmax=extent)
    ax.set(yticks=range(len(grid)),yticklabels=grid.index,xticks=range(len(grid.columns)),xticklabels=grid.columns,title=nature+' · minimum free cash / starting capital, over each observed prefix')
    ax.tick_params(axis='x',rotation=25)
    for i in range(len(cash)):
        for j in range(len(cash.columns)):ax.text(j,i,f'{cash.iloc[i,j]:.2f}',ha='center',va='center',fontsize=8)
    fig.colorbar(im,ax=ax,label='Cash encumbrance diagnostic, not an investment return')
    fig.savefig(args.output/'minimum_free_cash.png',dpi=160);plt.close(fig)
    flags=['failed_nonpositive_equity','failed_known_boundary_exit','failed_proxy_collateral_shortfall']
    fig,ax=plt.subplots(figsize=(13,6),constrained_layout=True)
    for i,flag in enumerate(flags):
        counts=[int(summary[summary.stress_case.eq(case['name'])].all_failure_flags.fillna('').str.contains(flag).sum()) for case in CASES]
        ax.barh(np.arange(len(CASES))+(i-1)*.23,counts,height=.23,label=flag)
    ax.set(yticks=range(len(CASES)),yticklabels=[x['name'] for x in CASES],xlabel='Accounts; failure flags can overlap',title=nature+' · preserve simultaneous causes')
    ax.legend(fontsize=8);fig.savefig(args.output/'failure_flags.png',dpi=160);plt.close(fig)
    report=['# Longer outages, adverse prices and collateral pressure','',nature+'. Nine scenarios × eight funded accounts = 72 dependent paths. All magnitudes and windows were fixed before results.','',
      '## Read the experiment correctly','',
      'Outages last 10/20 scheduled sessions; reserve can rise from 10% to 40% of gross. A 5%/10% additive leg-price step is adverse to the frozen baseline side, using its last available absolute USD settlement through d−2. Both spread members can move against their respective sides: this is a basis deformation, not a common parallel move. Steps persist after the outage rather than creating a favorable automatic rebound. Fixed annual cohorts and signs do not move or flip when the stressed account differs.','',
      'Historical signal directions, contract selection and unit-risk reference histories stay fixed. Shocked references affect actual VM, execution and collateral; only lagged shocked price history enters the gross price basis. This conditional fixed-policy test is not a fully re-estimated trading system or a calibrated market equilibrium. Missing quotes stay missing, negative references are allowed, and costs remain the original fixed assumptions.','',
      'Each account has its own baseline-directed adverse path. Cross-strategy alpha, a shared-market benchmark comparison and confidence intervals for such a premium would be inappropriate here; none are supplied. Earlier historical research and failed paths remain available.','',
      '## Every result, including stopped prefixes','',
      '|Case|Account|Primary status|End date|Min equity USD|Min free cash USD|Max collateral shortfall USD|','|---|---|---|---|---:|---:|---:|']
    for r in summary.itertuples(index=False):report.append(f'|{r.stress_case}|{r.account_case}/{r.strategy}|{r.status}|{r.stop_date}|{r.minimum_equity:,.2f}|{r.minimum_free_cash:,.2f}|{r.max_cash_shortfall:,.2f}|')
    report+=['','Different stop dates imply different observed horizons. Prefix minima are diagnostics, not comparable full-period return/risk estimates. Severity need not monotonically rank ending dollars once accounts stop.','',
      '![Joint-stress completion and stops](completion.png)','','![Minimum free cash](minimum_free_cash.png)','','## Failure causes and paired exposure','',
      '![Overlapping failure flags](failure_flags.png)','','The selected primary status follows the existing engine; all simultaneous equity, delivery-boundary and cash-shortfall events remain in all_failure_flags and the event logs. A 50% risk-buffer breach alone is not insolvency. No deadline extension, external top-up, new price floor or unobserved liquidation is used.','',
      'Both spread legs reduce equal units bounded by the weaker current offer and shared daily sides. A zero-capacity member blocks the paired fill. New risk is gated against both day-start and planned post-reduction inventory, retaining v0.7.1. Reserve is encumbered cash, not another expense: equity = prior equity + VM − costs. Terminal reconciliation uses shocked open-position marks together with shocked fills.','',
      '## Reproduction and evidence','',
      'Inspect FROZEN_RUN.json, FROZEN_COHORTS.csv, FROZEN_LEGS.csv, summary.csv and RUN_MANIFEST.json. Account price_events.csv records signed USD steps; its hypothetical full-baseline-leg impulse is not the account’s realized P&L. Compare actual pnl/holdings/trades, admissions, exit plans and stress budgets/sessions. terminal_inventory.csv preserves remaining legs, mark offsets, deadline, offered/used/remaining capacity, cash and every failure flag.','',
      'Reproduce: python -m strategy_lab.commodities.joint_report --fixture --output NEW_DIRECTORY. Licensed work uses --input PRIVATE_INPUT --cohorts FROZEN_PRIVATE_CSV --legs FROZEN_PRIVATE_LEGS; keep outputs private.','',
      'Scheduled calendars, current-vintage metadata and missing first-position archives remain limitations. Reserve is a proxy without historical SPAN/spread credits or broker add-ons. EOD paired references are not intraday queues, real close-out or proven tradability. This deterministic conditional stress has no occurrence-probability, worst-possible-shock or unseen-OOS claim. Only original code/methods/tests and invented inputs are public; licensed sources, anchors, event dates and all real derived findings stay private. Research direction was selected by Mingju Zhang; implementation/experiments were AI-assisted and unaided review remains separately tracked.']
    (args.output/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    receipt=dict(created_utc=datetime.now(timezone.utc).isoformat(),data_kind=manifest['data_kind'],package_version=__version__,
      paths=len(summary),completed=int((~summary.status.str.startswith('failed')).sum()),failed=int(summary.status.str.startswith('failed').sum()),
      maximum_cash_error=float(summary.reconciliation_error.abs().max()),runtime_seconds=time.perf_counter()-started,
      files={f.relative_to(args.output).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.rglob('*') if f.is_file()})
    (args.output/'RUN_MANIFEST.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2),flush=True)


if __name__=='__main__':main()
