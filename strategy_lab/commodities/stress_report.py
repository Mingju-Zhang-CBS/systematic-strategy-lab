"""Frozen-cohort post-admission stress: offline fixture or private licensed input."""
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
from .research_report import write_result,summarize,monthly_account,paired_inference
from .stress import CASES,compile_stress,entry_cohorts


ACCOUNTS=[('base',x) for x in ['long_only','trend','carry','bm_outright','bm_spread','trend_half','carry_half']]+[('delay_plus_3','carry')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',action='store_true')
    mode.add_argument('--input',type=Path)
    parser.add_argument('--cohorts',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.fixture and args.cohorts is None:
        parser.error('private experiments require separately frozen --cohorts')
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter()
    if args.fixture:
        q,c,manifest=research_frames()
        protocol=ResearchProtocol(start='2021-01-01',end='2022-12-31')
        supplied=None
    else:
        q=pd.read_csv(args.input/'quotes.csv.gz')
        c=pd.read_csv(args.input/'contracts.csv')
        manifest=json.loads((args.input/'manifest.json').read_text())
        for name,sha in manifest['files'].items():
            if hashlib.sha256((args.input/name).read_bytes()).hexdigest()!=sha:
                raise ValueError('input fingerprint mismatch: '+name)
        supplied=pd.read_csv(args.cohorts)
        protocol=ResearchProtocol()
    protocol=replace(protocol,execution_policy='staged',exit_lead=10,entry_budget=True)
    code={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}
    frozen=dict(created_utc=datetime.now(timezone.utc).isoformat(),data_kind=manifest['data_kind'],source=manifest,
                cases=CASES,accounts=ACCOUNTS,protocol=protocol.__dict__,code=code,
                cohort_sha256=None if supplied is None else hashlib.sha256(args.cohorts.read_bytes()).hexdigest(),
                hypothesis='Fixed post-admission supply/margin stresses; no return-selected scenarios or changed stopping boundaries',
                clocks='Five-day shocks from next scheduled session. Offer surprises at execution, history visible with t-2 delay; current-day margin announcement before decisions.',
                scope='Prior inspected historical paths; no new unseen OOS or 56-independent-observation claim')
    (args.output/'FROZEN_RUN.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    tape=prepare(q,c,manifest,liquidity_window=5,monotone_roll=True)
    summaries=[]
    all_cohorts=[]
    months={case['name']:{} for case in CASES}
    windows=[]
    for account_case,name in ACCOUNTS:
        config=replace(protocol,extra_delay=3 if account_case=='delay_plus_3' else 0,
                       capital=500_000 if name.endswith('_half') else 1_000_000)
        strategy=name.removesuffix('_half')
        baseline=run_research(tape,strategy,config)
        cohorts=entry_cohorts(baseline['trades'],strategy=='bm_spread') if supplied is None else supplied[(supplied.account_case==account_case)&(supplied.account==name)].copy()
        all_cohorts.append(cohorts.assign(account_case=account_case,account=name))
        baseline_ledger=baseline['ledger']
        for case in CASES:
            stress=None if case['name']=='control' else compile_stress(tape,cohorts,case)
            result=baseline if stress is None else run_research(tape,strategy,config,stress=stress)
            path=args.output/case['name']/account_case/name
            write_result(result,path,detail=True)
            if stress is not None:
                for table in ('stress_budgets','stress_sessions'):
                    result[table].to_csv(path/(table+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
                stress.windows.to_csv(path/'stress_windows.csv',index=False)
                windows.append(stress.windows.assign(stress_case=case['name'],account_case=account_case,account=name))
            l=result['ledger']
            r=summarize(result,account_case)
            r.update(stress_case=case['name'],account_case=account_case,strategy=name,frozen_cohorts=len(cohorts),
                     proxy_margin_failure=result['events'].code.eq('failed_proxy_collateral_shortfall').any(),
                     risk_buffer_breach_days=0 if stress is None else int(result['stress_sessions'].risk_buffer_breach.sum()),
                     no_projected_capacity_checks=0 if stress is None else int(result['stress_budgets'].no_projected_capacity.sum()),
                     insufficient_drain_checks=0 if stress is None else int(result['stress_budgets'].budget_slack.le(0).sum()),
                     offered_zero_checks=0 if stress is None else int(result['stress_budgets'].offered_capacity.eq(0).sum()),
                     shocked_exposure_days=0 if stress is None else int(result['stress_sessions'].shocked_held_contracts.gt(0).sum()),
                     maximum_collateral_shortfall=0 if stress is None else float(result['stress_sessions'].collateral_shortfall.max()))
            summaries.append(r)
            if account_case=='base':
                months[case['name']][name]=monthly_account(l,config,tape.dates)
                l[['session','opening_equity','equity','positions','stale_contracts']].to_csv(args.output/(case['name']+'_'+name+'_daily.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
            print(case['name'],account_case,name,result['status'],r['stop_date'],flush=True)
    cohorts=pd.concat(all_cohorts,ignore_index=True)
    cohorts.to_csv(args.output/'FROZEN_COHORTS.csv',index=False)
    summary=pd.DataFrame(summaries)
    summary.to_csv(args.output/'summary.csv',index=False)
    pd.concat(windows,ignore_index=True).to_csv(args.output/'all_windows.csv',index=False)
    inference=[]
    for case in CASES:
        values=months[case['name']]
        sleeves=[pd.read_csv(args.output/(case['name']+'_'+n+'_daily.csv.gz')).set_index('session') for n in ('trend_half','carry_half')]
        common=sleeves[0].index.intersection(sleeves[1].index)
        mix=(sleeves[0].loc[common]+sleeves[1].loc[common]).reset_index()
        values['half_mix']=monthly_account(mix,protocol,tape.dates)
        h=paired_inference(values,{'synthetic_demo':('2021-01','2022-12')} if args.fixture else None)
        inference.append(h.assign(stress_case=case['name']))
    inference=pd.concat(inference,ignore_index=True)
    inference.to_csv(args.output/'paired_inference.csv',index=False)
    plt.rcParams.update({'figure.facecolor':'#faf8f3','axes.facecolor':'#faf8f3','font.size':9})
    nature='INVENTED INPUTS' if args.fixture else 'PRIVATE real references + hypothetical stresses'
    grid=summary.assign(account=summary.account_case+'/'+summary.strategy).pivot(index='stress_case',columns='account',values='status').reindex([x['name'] for x in CASES])
    complete=~grid.apply(lambda s:s.str.startswith('failed'))
    fig,ax=plt.subplots(figsize=(13,5),constrained_layout=True)
    ax.imshow(complete.to_numpy().astype(int),vmin=0,vmax=1,cmap=matplotlib.colors.ListedColormap(['#b05754','#36b3a8']),aspect='auto')
    ax.set_xticks(range(len(grid.columns)),grid.columns,rotation=25,ha='right')
    ax.set_yticks(range(len(grid)),grid.index)
    ax.set_title(nature+' · completion under fixed shocks, not profit or guaranteed fills')
    for i in range(len(grid)):
        for j in range(len(grid.columns)):
            ax.text(j,i,'complete' if complete.iloc[i,j] else 'STOP',ha='center',va='center',fontsize=8)
    fig.savefig(args.output/'completion.png',dpi=160)
    plt.close(fig)
    totals=summary.groupby('stress_case',sort=False)[['risk_buffer_breach_days','no_projected_capacity_checks','insufficient_drain_checks','offered_zero_checks']].sum().reindex([x['name'] for x in CASES])
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    for ax,column in zip(axes.flat,totals):
        ax.barh(totals.index,totals[column],color='#36b3a8')
        ax.set(title=column.replace('_',' '),xlabel='Account-days or product-day checks; not independent samples')
    fig.suptitle(nature+' · preserve shortages, including recovery after a shock')
    fig.savefig(args.output/'budget_and_funding.png',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,6),constrained_layout=True)
    for ax,claim in zip(axes,['bm_increment','bm_spread_mean']):
        h=inference[inference.claim.eq(claim)&inference.phase.isin(['confirmation','synthetic_demo'])]
        for i,case in enumerate(CASES):
            for offset,block in [(-.12,6),(.12,12)]:
                r=h[h.stress_case.eq(case['name'])&h.block.eq(block)].iloc[0]
                if np.isfinite(r['mean']):
                    ax.hlines(i+offset,100*r.lower,100*r.upper,color='#36b3a8' if block==6 else '#657ba5')
                    ax.plot(100*r['mean'],i+offset,'o',ms=3,color='#101928')
                else:
                    ax.text(.02,i+offset,'not evaluable',transform=ax.get_yaxis_transform(),fontsize=7)
        ax.axvline(0,color='grey',ls='--')
        ax.set(yticks=range(len(CASES)),yticklabels=[x['name'] for x in CASES],title=claim,xlabel='Mean monthly pp; 6 / 12-month blocks')
    fig.suptitle(nature+' · failed comparisons retained; history already inspected')
    fig.savefig(args.output/'historical_intervals.png',dpi=160)
    plt.close(fig)
    report=['# Post-admission capacity and collateral stress','',nature+'. Fixed events and parameters; no return tuning. This is a robustness test of modeled execution, not actual SPAN, calibrated supply or new independent OOS.','',
        '## Experiment','',
        'Seven cases × eight funded accounts = 56 paths. Cases use fixed five-session half/quarter/one-leg-quarter/zero capacity offers, doubled proxy collateral, and a combined quarter-capacity/fourfold-collateral case. The existing $2.50/side, ticks, risk sizing, entry budget and hard boundary are retained.','',
        'Freeze each product/year first baseline addition; shock its fixed contracts from the next scheduled day. Events do not move when the stressed account takes a different path. Capacity is hypothetical available participation, not edited vendor volume. Current surprises affect fills; only observations ending d−2 affect planning. Announced current-day reserve multipliers affect funding, and overlaps use max rather than compound.','',
        '## Every path, including failures','',
        '|Case|Account|Status|End|Observed ending USD|Costs USD|','|---|---|---|---|---:|---:|']
    for r in summary.itertuples(index=False):
        report.append(f'|{r.stress_case}|{r.account_case}/{r.strategy}|{r.status}|{r.stop_date}|{r.terminal_equity:,.2f}|{r.costs:,.2f}|')
    report+=['','Stopped paths have different horizons: ending dollars are not comparable full-period returns. These paths share data, signals and shock schedules; 56 paths are not 56 independent statistical observations.','',
        '![Fixed stress completion](completion.png)','','## Budget and funding diagnostics','',
        'Retirement may receive a smaller paired fill than its frozen request. The weaker leg and cumulative used sides bound both legs together. Optional additions remain whole-request. A refusal cannot restore outgoing inventory. Zero supply retains old risk; no liquidation is invented.','',
        'Above the 50% reserve/equity risk buffer, lagged value and the announced rate request proportional integer paired reductions and block new risk. A buffer breach is distinct from actual modeled collateral exceeding all cash at EOD. The latter stops as failed_proxy_collateral_shortfall; neither outside funding nor a reserve-as-expense debit is introduced.','',
        '![Budget and funding shortages](budget_and_funding.png)','','## Historical economic comparisons','',
        'The same two claims, 6/12-month moving blocks, 5,000 draws and Holm family size two remain. Failed/incomplete months are not silently dropped; missing comparisons are not evaluable. Inspect paired_inference.csv for every phase and case. Already-inspected history does not become unseen OOS after a new split.','',
        '![Historical intervals or explicit failure](historical_intervals.png)','','## Read the evidence','',
        'FROZEN_RUN.json binds inputs, code and cases. FROZEN_COHORTS.csv fixes events; all_windows.csv preserves schedules even when unexposed. Per-account stress_budgets.csv.gz distinguishes conservative known capacity from offered current supply, time to the old deadline and drainage slack. stress_sessions.csv.gz separates risk-buffer breaches from cash shortfalls. Compare those with exit_plans, admissions, ordered fills and cash ledgers. A qualified entry does not reserve future liquidity.','',
        'Source unit blockers, scheduled calendars, current-vintage contract evidence, missing historical first-position notices and proxy reserves retain their limitations. Only original code/methods and invented fixtures are publishable here. Licensed sources, their cohorts and all real derived results remain private. Research direction was selected by Mingju Zhang; implementation/experiments were AI-assisted and unaided review is tracked separately.','',
        'Reproduce: python -m strategy_lab.commodities.stress_report --fixture --output NEW_DIRECTORY. For licensed research, use --input PRIVATE_INPUT --cohorts FROZEN_PRIVATE_CSV and keep outputs private.']
    (args.output/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    receipt=dict(created_utc=datetime.now(timezone.utc).isoformat(),data_kind=manifest['data_kind'],package_version=__version__,
                 paths=len(summary),completed=int((~summary.status.str.startswith('failed')).sum()),failed=int(summary.status.str.startswith('failed').sum()),
                 maximum_cash_error=float(summary.reconciliation_error.abs().max()),runtime_seconds=time.perf_counter()-started,
                 files={str(f.relative_to(args.output)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in args.output.rglob('*') if f.is_file()})
    (args.output/'RUN_MANIFEST.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2),flush=True)


if __name__=='__main__':
    main()
