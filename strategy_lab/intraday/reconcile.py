"""Independent reconstruction from orders; does not reuse the engine's balance."""
import numpy as np
import pandas as pd


def reconcile_ledger(daily,orders,bars,quotes,config):
    """Audit cash, shares, quote capacity, costs and retained closing exposure."""
    d=daily.copy();q=quotes.copy();b=bars.copy()
    o=orders.reindex(columns=['session','shares','price','fee_slippage','fill_time','decision'])
    # A quoted attempt with zero admitted shares still advances the engine's
    # financing clock. Missing-quote attempts do not.
    o=o.loc[o.fill_time.notna()].copy()
    o['fill_time']=pd.to_datetime(o.fill_time,utc=True,format='mixed')
    o['decision']=pd.to_datetime(o.decision,utc=True,format='mixed')
    q['quote_time']=pd.to_datetime(q.quote_time,utc=True,format='mixed')
    b['bar_end']=pd.to_datetime(b.bar_end,utc=True,format='mixed')
    b['session']=b.bar_end.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    if q.quote_time.duplicated().any():raise ValueError('Unique single-asset quote clocks required')
    fills=o.merge(q,left_on='fill_time',right_on='quote_time',how='left',suffixes=('','_quote'),validate='many_to_one')
    buying=fills.shares>0
    expected_price=np.where(buying,fills.ask,fills.bid)
    expected_capacity=np.where(buying,fills.ask_size,fills.bid_size)
    bad_time=((fills.fill_time<fills.decision+pd.to_timedelta(config.delay_seconds,unit='s'))
              |(fills.fill_time>fills.decision+pd.to_timedelta(config.delay_seconds+config.wait_seconds,unit='s')))
    bad_quote=(~np.isfinite(expected_price)|(abs(fills.price-expected_price)>1e-9)
               |(abs(fills.shares)>expected_capacity)) & fills.shares.ne(0)
    bad_fee=abs(fills.fee_slippage-abs(fills.shares)*(config.fee_per_share+config.slippage_per_share))>1e-8
    cash=config.initial_cash;position=0;rows=[]
    for day in d.itertuples():
        day_bars=b.loc[b.session.eq(day.session)]
        opened=pd.Timestamp(day_bars.session_open.iloc[0]);closed=pd.Timestamp(day_bars.session_close.iloc[0])
        decision_bars=day_bars.loc[day_bars.bar_end<closed-pd.Timedelta(seconds=60)]
        previous_time=opened;last_mark=0.;finance=borrow=0.;bad_admissions=0
        for fill in fills.loc[fills.session.eq(day.session)].itertuples():
            observed=decision_bars.loc[decision_bars.bar_end<=fill.decision]
            if not observed.empty and observed.bar_end.iloc[-1]>previous_time:last_mark=float(observed.close.iloc[-1])
            years=(fill.fill_time-previous_time).total_seconds()/(365*86400)
            cost_f=max(-cash,0)*config.financing_rate*years
            cost_b=max(-position,0)*last_mark*config.borrow_rate*years
            cash-=cost_f+cost_b;finance+=cost_f;borrow+=cost_b
            old_position=position
            cash-=fill.shares*fill.price+fill.fee_slippage;position+=int(fill.shares)
            last_mark=(fill.bid+fill.ask)/2;previous_time=fill.fill_time
            opened_risk=(position!=0 and (old_position*position<=0 or abs(position)>abs(old_position)))
            if opened_risk and cash+position*last_mark < config.initial_margin_fraction*abs(position)*last_mark-1e-7:bad_admissions+=1
        if not decision_bars.empty and decision_bars.bar_end.iloc[-1]>previous_time:last_mark=float(decision_bars.close.iloc[-1])
        years=(closed-previous_time).total_seconds()/(365*86400)
        cost_f=max(-cash,0)*config.financing_rate*years
        cost_b=max(-position,0)*last_mark*config.borrow_rate*years
        cash-=cost_f+cost_b;finance+=cost_f;borrow+=cost_b
        mark=float(day_bars.close.iloc[-1])
        rows.append({'session':day.session,'reconstructed_cash':cash,
                     'cash_error':cash-day.cash,'position_error':position-day.remaining_shares,
                     'equity_error':cash+position*mark-day.equity,
                     'financing_error':finance-day.financing,'borrow_error':borrow-day.borrow,
                     'bad_new_risk_admissions':bad_admissions,
                     'retained_shares':position,'reported_status':day.status})
    result=pd.DataFrame(rows)
    summary={'cash_and_position_match':bool((result.cash_error.abs()<1e-7).all() & result.position_error.eq(0).all()),
             'equity_matches_last_mark':bool((result.equity_error.abs()<1e-7).all()),
             'bad_fill_times':int(bad_time.sum()),'bad_quote_price_or_capacity':int(bad_quote.sum()),
             'bad_fee_calculations':int(bad_fee.sum()),
             'funding_recomputed':bool((result.financing_error.abs()<1e-7).all() & (result.borrow_error.abs()<1e-7).all()),
             'bad_new_risk_admissions':int(result.bad_new_risk_admissions.sum()),
             'stopped_with_retained_risk':bool(d.status.iloc[-1]=='stopped_unclosed_risk'),
             'remaining_shares':int(d.remaining_shares.iloc[-1])}
    return result,summary
