"""Original invented known-answer examples; no licensed market observations."""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from strategy_lab.intraday.actions import action_table
from strategy_lab.intraday.reference import effr_reference,cash_benchmark


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('local-runs/intraday-clocks'));a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    observations=pd.DataFrame({'effectiveDate':['2023-01-04','2023-01-05','2023-01-06','2023-01-09','2023-01-10'],
                               'percentRate':[3.,4.,5.,6.,7.]})
    sessions=pd.DataFrame({'session':['2023-01-06','2023-01-09','2023-01-10'],
        'open':['2023-01-06T14:30Z','2023-01-09T14:30Z','2023-01-10T14:30Z'],
        'close':['2023-01-06T21:00Z','2023-01-09T21:00Z','2023-01-10T21:00Z']})
    plt.rcParams.update({'figure.facecolor':'#FAF9F5','axes.facecolor':'#FAF9F5','axes.spines.top':False,'axes.spines.right':False})
    fig,ax=plt.subplots(figsize=(8,4),layout='constrained')
    totals={}
    for clock,color in [('14:45','#101928'),('09:15','#36B3A8')]:
        result=cash_benchmark(sessions,effr_reference(observations,clock))
        result.to_csv(a.output/f'cash-{clock.replace(":","")}.csv',index=False)
        totals[clock]=float(result.benchmark_cash.iloc[-1]-100000)
        ax.plot(pd.to_datetime(result.session),result.benchmark_cash-100000,marker='o',color=color,label=clock+' ET availability proxy')
    ax.set(title='Invented cash rates: release timing changes opportunity cost',ylabel='Accrued proxy interest on USD 100k (USD)',xlabel='Valuation date')
    ax.legend();fig.savefig(a.output/'cash_clock.png',dpi=160);plt.close(fig)
    daily=pd.DataFrame({'permno':[1,1,1],'dlycaldt':['2020-01-02','2020-01-03','2020-01-06'],
        'dlyprc':[100.,99.,49.5],'dlyprevprc':[100.,100.,99.],'dlyret':[0.,0.,0.],
        'dlyorddivamt':[0.,1.,0.],'dlynonorddivamt':[0.,0.,0.],'dlydistretflg':['NO','C1','S1']})
    events=pd.DataFrame({'permno':[1,1],'disexdt':['2020-01-03','2020-01-06'],'disseqnbr':[1,1],
        'disdeclaredt':[None,'2020-01-02'],'disdivamt':[1.,0.],'disfacshr':[0.,1.],
        'distype':['CD','FRS'],'dispaymenttype':['USD','SHR'],'disorigcurtype':['USD','N/A']})
    identity=pd.DataFrame({'permno':[1],'ticker':['SYNTH'],'secinfostartdt':['2019-01-01'],'secinfoenddt':['2021-12-31']})
    actions,issues=action_table(daily,events,identity)
    actions.to_csv(a.output/'actions.csv',index=False);issues.to_csv(a.output/'blockers.csv',index=False)
    (a.output/'REPORT.md').write_text('# Information Clocks and Action Units\n\nAll values and security identifiers in this report are **invented known-answer fixtures**.\n\n![Cash timing](cash_clock.png)\n\n'
        f'The USD 100k opportunity-cost account earns ${totals["14:45"]:.6f} under the primary 14:45 clock and ${totals["09:15"]:.6f} under the retained 09:15 clock. '
        'These are arithmetic examples, not observed EFFR or attainable investment returns. The Friday-to-Monday interval accrues three calendar days using the rate already available at Friday close. Neither benchmark changes strategy orders.\n\n'
        'The separate action example has a $1 cash distribution: `(99 + 1) / 100 − 1 = 0`. Its missing declaration clock still blocks use before the ex-date open. '
        'A declared 2-for-1 split gives `49.5 × 2 / 99 − 1 = 0`. A correct amount does not establish its historical publication time. '
        'These adjustments affect reference prices and lagged total-return features; the intraday account receives no dividend for overnight shares it did not hold.\n\n'
        '[Methods and limits](../../docs/INTRADAY_SOURCE_AUDIT.md) · [Tests](../../tests/test_intraday_actions.py)\n',encoding='utf-8')
    package=Path(__file__).resolve().parents[1]/'strategy_lab/intraday'
    (a.output/'run.json').write_text(json.dumps({'data_kind':'synthetic-known-answer','initial_cash':100000,
        'clocks':['14:45','09:15'],'day_count':'ACT/360','source_sha256':{n:hashlib.sha256((package/n).read_bytes()).hexdigest() for n in ['reference.py','actions.py']},
        'example_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
    print(json.dumps({'synthetic_interest_usd':totals,'retained_action_blockers':len(issues)}))


if __name__=='__main__':main()
