from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from strategy_lab.core import Config,arrays,backtest,metrics,rebalance,synthetic_market,validate_market

SMALL=Config(lookback=10,skip=2,covariance_window=5,dividend_payment_lag=3)

def test_ledger_conservation_and_no_overdraft_or_shorting():
    d,dec,orders=backtest(synthetic_market(100),SMALL)
    assert d.bridge_error.abs().max()<1e-7
    assert d.cash.min()>=0
    assert (d.filter(like="shares_")>=0).all().all()
    assert (d.shares_QQQ==0).all()
    assert (pd.to_datetime(orders.execution_date)>pd.to_datetime(orders.decision_date)).all()
    assert dec.filter(like="weight_").sum(axis=1).max()<=.99+1e-12
    assert dec.filter(like="weight_").max().max()<=.5+1e-12

def test_future_changes_do_not_rewrite_past_decisions_or_account():
    source=synthetic_market(180);changed=source.copy()
    cutoff=sorted(source.date.unique())[120]
    changed.loc[changed.date>=cutoff,"close"]*=1.3
    a,ad,ao=backtest(source,SMALL);b,bd,bo=backtest(changed,SMALL)
    pd.testing.assert_frame_equal(a[a.date<cutoff],b[b.date<cutoff])
    pd.testing.assert_frame_equal(ad[ad.date<cutoff],bd[bd.date<cutoff])
    pd.testing.assert_frame_equal(ao[ao.execution_date<cutoff],bo[bo.execution_date<cutoff])

def test_raw_split_and_delayed_dividend_preserve_wealth():
    data=synthetic_market(30)
    data["close"]=100.;data["cash_rate"]=0.;data["dividend"]=0.;data["split"]=1.
    dates=sorted(data.date.unique());ex=dates[15]
    data.loc[(data.ticker=="SPY")&(data.date>=ex),"close"]=49.
    data.loc[(data.ticker=="SPY")&(data.date==ex),["split","dividend"]]=[2.,1.]
    d,_,_=backtest(data,replace(SMALL,cost_bps=0),mode="spy")
    before=d.loc[d.date==dates[14]].iloc[0];event=d.loc[d.date==ex].iloc[0]
    assert event.nav==pytest.approx(before.nav)
    assert event.shares_SPY==2*before.shares_SPY
    assert event.receivable==pytest.approx(event.shares_SPY)
    paid=d.loc[d.date==dates[18]].iloc[0]
    assert paid.receivable==pytest.approx(0)
    assert paid.dividend_payment==pytest.approx(event.receivable)
    assert paid.nav==pytest.approx(event.nav)
    _,_,_,_,returns,_,_=arrays(data)
    assert returns[15,0]==pytest.approx(0)

def test_rebalance_accounts_for_both_sides_cost_and_unspendable_receivables():
    shares,cash,trade,fee=rebalance(np.array([10.,0]),0.,1000.,np.array([100.,100.]),np.array([0.,1.]),100)
    assert trade.tolist()==[-10,9]
    assert fee==pytest.approx(19)
    assert cash==pytest.approx(81)
    np.testing.assert_array_equal(shares,[0,9])
    shares,cash,_,_=rebalance(np.zeros(2),0.,1000.,np.array([100.,100.]),np.array([.5,.5]),3)
    assert np.all(shares==0) # NAV consisting only of receivables cannot fund a trade.

def test_costs_reduce_passive_terminal_nav_and_first_loss_counts_in_drawdown():
    data=synthetic_market(100)
    a,_,_=backtest(data,replace(SMALL,cost_bps=0),mode="spy")
    b,_,_=backtest(data,replace(SMALL,cost_bps=30),mode="spy")
    assert b.nav.iloc[-1]<a.nav.iloc[-1]
    tiny=pd.DataFrame({"date":pd.to_datetime(["2020-01-02","2020-01-03"]),"nav":[90.,95.],"prior_nav":[100.,90.],
                       "return":[-.1,95/90-1],"cash_return":[0.,0.],"turnover":[0.,0.],"cost":[0.,0.],"cash":[0.,0.],"bridge_error":[0.,0.]})
    assert metrics(tiny)["max_drawdown"]==pytest.approx(-.1)

def test_validation_rejects_duplicate_missing_sessions_and_bad_lags():
    data=synthetic_market(30)
    with pytest.raises(ValueError):validate_market(pd.concat([data,data.iloc[:1]]))
    with pytest.raises(ValueError):validate_market(data.iloc[1:])
    with pytest.raises(ValueError):backtest(data,replace(SMALL,execution_delay=0))
    with pytest.raises(ValueError):backtest(data.assign(close=np.nan),SMALL)
