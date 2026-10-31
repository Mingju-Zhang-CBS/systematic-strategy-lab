"""Current-vintage CRSP CIZ action adapter; no data redistribution implied."""
import numpy as np
import pandas as pd


def action_table(daily,events,identity):
    """Return dated adjustments and blockers; missing release evidence stays unknown.

    Cash uses ex-distribution amounts, not payment-day double credits. Accounts
    normally flatten intraday; these adjustments affect reference prices and
    trailing total returns, not a dividend credit for overnight shares not held.
    """
    d=daily.copy();e=events.copy();n=identity.copy()
    d['session']=pd.to_datetime(d.dlycaldt).dt.normalize()
    e['session']=pd.to_datetime(e.disexdt).dt.normalize()
    e['declaration_date']=pd.to_datetime(e.disdeclaredt)
    for col in ['secinfostartdt','secinfoenddt']:n[col]=pd.to_datetime(n[col])
    numeric=['dlyprc','dlyprevprc','dlyret','dlyorddivamt','dlynonorddivamt']
    if (d.duplicated(['permno','session']).any() or not np.isfinite(d[numeric]).all().all()
            or (d[['dlyprc','dlyprevprc']]<=0).any().any()
            or e.duplicated(['permno','session','disseqnbr']).any()
            or not np.isfinite(e[['disdivamt','disfacshr']]).all().all()):
        raise ValueError('Covered unique security days and finite distribution records required')
    mapped=d.merge(n[['permno','ticker','secinfostartdt','secinfoenddt']],on='permno',how='left')
    mapped=mapped.loc[mapped.session.between(mapped.secinfostartdt,mapped.secinfoenddt)].copy()
    if len(mapped)!=len(d) or mapped.duplicated(['permno','session']).any():
        raise ValueError('Every source day must have exactly one date-effective identity')
    results=[];issues=[];by_event={(int(k[0]),k[1]):g for k,g in e.groupby(['permno','session'])}
    for row in mapped.itertuples():
        key=(int(row.permno),row.session);g=by_event.get(key)
        cash=float(row.dlyorddivamt+row.dlynonorddivamt)
        split=1.;known=True;available=pd.NaT;reasons=[]
        if g is None:
            if cash!=0 or row.dlydistretflg!='NO':reasons.append('distribution_record_missing')
        else:
            cash_events=g.distype.isin(['CD','SD','CG','ROC','CP']) & g.dispaymenttype.eq('USD') & g.disorigcurtype.eq('USD')
            split_events=g.distype.isin(['FRS','SS']) & g.disdivamt.eq(0)
            if not (cash_events|split_events).all():reasons.append('unsupported_distribution')
            event_cash=float(g.loc[cash_events,'disdivamt'].sum())
            if abs(event_cash-cash)>1e-6:reasons.append('cash_distribution_mismatch')
            split=float(np.prod(1+g.disfacshr.to_numpy()))
            known=bool((g.declaration_date.notna() & (g.declaration_date<row.session)).all())
            if known:
                available=pd.Timestamp(g.declaration_date.max().date()).tz_localize('America/New_York')+pd.Timedelta(hours=23,minutes=59,seconds=59)
            else:reasons.append('action_publication_clock_unknown')
        reconstructed=(float(row.dlyprc)+cash)*split/float(row.dlyprevprc)-1
        if abs(reconstructed-float(row.dlyret))>1e-6:reasons.append('total_return_reconciliation_failed')
        if split<=0:reasons.append('invalid_split_ratio')
        for reason in reasons:issues.append({'asset':row.ticker,'session':row.session,'reason':reason,'severity':'blocker'})
        results.append({'asset':row.ticker,'session':row.session,'permno':row.permno,
                        'cash_dividend':cash,'split':split,'action_available_at':available,
                        'action_clock_known':known,'source_ready':not reasons,
                        'return_reconciliation_error':reconstructed-float(row.dlyret),
                        'evidence':'current_vintage_no_event' if g is None else 'current_vintage_distribution'})
    result=pd.DataFrame(results).sort_values(['asset','session']).reset_index(drop=True)
    if result.duplicated(['asset','session']).any():raise ValueError('Ambiguous ticker-day identity')
    return result,pd.DataFrame(issues,columns=['asset','session','reason','severity'])
