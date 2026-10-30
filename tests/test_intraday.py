from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from strategy_lab.intraday.engine import Config, backtest
from strategy_lab.intraday.demo import fixture


def test_fills_after_information_and_accounting():
    b,q=fixture();d,o,f=backtest(b,q)
    filled=o.loc[o.shares!=0]
    assert len(filled)>0
    assert (filled.fill_time >= filled.decision+pd.Timedelta(seconds=1)).all()
    assert (f.history_end < f.decision).all()
    assert (d.remaining_shares==0).all()
    cash=Config().initial_cash-(filled.shares*filled.price+filled.fee_slippage).sum()-d.financing.sum()-d.borrow.sum()
    assert d.cash.iloc[-1]==pytest.approx(cash)
    assert d.net_pnl.sum()==pytest.approx(d.cash.iloc[-1]-Config().initial_cash)


def test_future_perturbation():
    b,q=fixture();a,_,_=backtest(b,q)
    cutoff=b.session_open.drop_duplicates().iloc[30]
    changed=b.copy();changed.loc[changed.bar_end>=cutoff,'close']*=1.5
    c,_,_=backtest(changed,q)
    days=pd.to_datetime(a.session)<cutoff.tz_convert('America/New_York').tz_localize(None).normalize()
    pd.testing.assert_frame_equal(a.loc[days].reset_index(drop=True),c.loc[days].reset_index(drop=True))


def test_same_endpoint_quote_is_not_used_and_missing_exit_is_retained():
    b,q=fixture()
    d,o,_=backtest(b,q)
    last_session=d.session.iloc[0]
    close=b.loc[b.bar_end.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')==last_session,'session_close'].iloc[0]
    # The fixture's first evaluated session has an open position before flatten.
    current=o.loc[o.session==last_session]
    assert current.iloc[-1].reason=='close' and current.iloc[-1].shares!=0
    changed=q.loc[~q.quote_time.between(close-pd.Timedelta(seconds=59),close)].copy()
    failure,orders,_=backtest(b,changed)
    assert failure.status.iloc[-1]=='stopped_unclosed_risk'
    assert failure.remaining_shares.iloc[-1]!=0
    assert orders.iloc[-1].status=='missing_quote'
    endpoint=q.copy();endpoint['quote_time']-=pd.Timedelta(seconds=1)
    _,orders,_=backtest(b,endpoint)
    fills=orders.loc[orders.shares!=0]
    assert len(orders)>0
    assert fills.empty  # Endpoint is too early; the +59s quote is outside +1..+6s.


def test_early_close_and_partial_reduction():
    b,q=fixture();day=b.session_open.drop_duplicates().iloc[18]
    mask=b.session_open==day
    close=day+pd.Timedelta(hours=3.5)
    b.loc[mask,'session_close']=close
    b=b.loc[(~mask)|(b.bar_end<=close)].reset_index(drop=True)
    extra=q.iloc[:1].copy();extra['quote_time']=close-pd.Timedelta(seconds=59);extra['bid_size']=1;extra['ask_size']=1
    q=pd.concat([q,extra]).sort_values('quote_time').drop_duplicates(['asset','quote_time']).reset_index(drop=True)
    d,o,_=backtest(b,q)
    assert d.status.iloc[-1]=='stopped_unclosed_risk'
    assert o.iloc[-1].status=='partial_or_budget_limited'
    assert abs(o.iloc[-1].shares)==1


def test_reject_duplicate_and_bad_order():
    b,q=fixture()
    with pytest.raises(ValueError):backtest(b,pd.concat([q.iloc[:1],q]))
    with pytest.raises(ValueError):backtest(b.iloc[::-1],q)


def test_funding_budget_limits_new_risk():
    b,q=fixture();_,o,_=backtest(b,q,'vol_scaled',replace(Config(),initial_margin_fraction=1.))
    for r in o.loc[o.shares!=0].itertuples():
        equity=r.cash+r.position*r.price
        assert abs(r.position)*r.price<=equity+2
