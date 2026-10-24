from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from strategy_lab.real_data import FUNDS, load_snapshot, validate_nav
from strategy_lab.real_research import (RealConfig, backtest_real, paired_inference,
                                       real_metrics, rebalance_units, target_weights)


def small_market(n=180):
    dates = pd.bdate_range("2021-01-04",periods=n)
    rng = np.random.default_rng(39)
    r = rng.normal(.0004,.006,(n,5));r[:,0]=.0001
    values = 10*np.cumprod(1+r,axis=0)
    return pd.DataFrame({"date":dates,**{f:values[:,j] for j,f in enumerate(FUNDS)}})


SMALL = RealConfig(lookback=20,skip=3,covariance=10,start="2021-03-01")


def test_real_snapshot_is_complete_and_hash_bound():
    data,source,protocol=load_snapshot()
    assert len(data)==5639
    assert str(data.date.iloc[0].date())=="2003-06-02"
    assert str(data.date.iloc[-1].date())=="2025-12-31"
    assert source["data_kind"]=="public-real"
    assert protocol["segments"]["confirmation"]==["2020-01-01","2025-12-31"]


@pytest.mark.parametrize("mutation",["duplicate","missing","negative","dividend","unordered"])
def test_bad_nav_inputs_fail_closed(mutation):
    d=small_market()
    if mutation=="duplicate":d=pd.concat([d,d.iloc[:1]],ignore_index=True)
    if mutation=="missing":d.loc[30,"C"]=np.nan
    if mutation=="negative":d.loc[30,"G"]=-1
    if mutation=="dividend":d["dividend"]=1.
    if mutation=="unordered":d=d.iloc[::-1]
    with pytest.raises(ValueError):validate_nav(d)


def test_request_follows_assumed_publication_and_observation():
    _,decisions,orders=backtest_real(small_market(),SMALL)
    for row in decisions.itertuples():
        if row.status!="scheduled":continue
        assert pd.Timestamp(row.request_at)>pd.Timestamp(row.assumed_available_after)
        assert pd.Timestamp(row.request_at).hour==11
        assert row.posting_date==str(pd.Timestamp(row.request_at).date())
        assert row.max_feature_date==row.observation_date
    assert not orders.empty
    with pytest.raises(ValueError):backtest_real(small_market(),replace(SMALL,execution_delay=1))


def test_future_prices_do_not_rewrite_past_decisions_or_balances():
    data=small_market();changed=data.copy();cut=data.date.iloc[120]
    changed.loc[changed.date>=cut,[*FUNDS]]=changed.loc[changed.date>=cut,[*FUNDS]]*1.6
    a,ad,ao=backtest_real(data,SMALL);b,bd,bo=backtest_real(changed,SMALL)
    date=str(cut.date())
    pd.testing.assert_frame_equal(a[a.date<date],b[b.date<date])
    pd.testing.assert_frame_equal(ad[ad.observation_date<date],bd[bd.observation_date<date])
    pd.testing.assert_frame_equal(ao[ao.posting_date<date],bo[bo.posting_date<date])


def test_unknown_posting_price_changes_units_but_not_frozen_targets():
    data=small_market();_,before,_=backtest_real(data,SMALL)
    first=before.iloc[0]
    changed=data.copy();post=pd.Timestamp(first.posting_date)
    changed.loc[changed.date==post,"C"]*=1.25
    _,after,orders=backtest_real(changed,SMALL)
    pd.testing.assert_series_equal(before.iloc[0],after.iloc[0])
    executed=orders[orders.decision_id==first.decision_id]
    assert executed.loc[executed.fund=="C","posting_nav"].iloc[0]==pytest.approx(changed.loc[changed.date==post,"C"].iloc[0])


def test_two_leg_fees_are_funded_without_external_cash():
    units=np.array([1000.,0,0,0,0]);prices=np.ones(5)*100
    weights=np.array([0.,0.,1.,0.,0.])
    result,fee,gross,dollars=rebalance_units(units,prices,weights,10)
    # $100,000 sold from G plus the after-fee C purchase: V_after=V_before*(1-r)/(1+r).
    expected=100000*(1-.001)/(1+.001)
    assert result@prices==pytest.approx(expected)
    assert fee==pytest.approx(100000-expected)
    assert gross==pytest.approx(100000+expected)
    assert dollars.sum()+fee==pytest.approx(0,abs=1e-8)


def test_accumulation_income_is_counted_once_and_never_as_extra_cash():
    data=small_market();data.loc[:,list(FUNDS)]=100.
    event=data.date.iloc[80];data.loc[data.date>=event,"C"]=102.
    ledger,_,_=backtest_real(data,replace(SMALL,cost_bps=0),"C_buy_hold")
    assert ledger.nav.iloc[-1]==pytest.approx(102000.)
    assert ledger.cash_dividend_added.sum()==0
    assert ledger.extra_operating_expense.sum()==0
    assert ledger.bridge_error.abs().max()<1e-7


def test_every_day_and_transfer_conserves_funding_and_target_limits():
    ledger,decisions,orders=backtest_real(small_market(),SMALL)
    assert ledger.bridge_error.abs().max()<1e-7
    assert (ledger.filter(like="units_")>=0).all().all()
    targets=decisions[[f"target_{f}" for f in FUNDS]]
    np.testing.assert_allclose(targets.sum(axis=1),1)
    np.testing.assert_allclose(targets.to_numpy()*100,np.round(targets.to_numpy()*100))
    assert decisions[[f"target_{f}" for f in FUNDS[1:]]].max().max()<=.5
    assert decisions.target_G.min()>=.01-1e-12
    assert orders.groupby("posting_date").first().index.str[:7].value_counts().max()<=2


def test_static_and_momentum_share_risk_scaler_when_all_assets_qualify():
    data=small_market();prices=np.cumprod(np.ones((80,5))*1.001,axis=0)
    returns=np.vstack([np.zeros(5),prices[1:]/prices[:-1]-1])
    a=target_weights(prices,returns,60,"momentum",SMALL)
    b=target_weights(prices,returns,60,"risk_matched_static",SMALL)
    np.testing.assert_array_equal(a[0],b[0])
    assert a[2]==b[2]
    prices[:,1:]=np.cumprod(np.ones((80,4))*.999,axis=0)
    a=target_weights(prices,returns,60,"momentum",SMALL)
    assert a[0][0]==1.


def test_passive_friction_is_monotone_and_g_reserve_is_not_double_credited():
    data=small_market()
    free=backtest_real(data,replace(SMALL,cost_bps=0),"C_buy_hold")[0]
    costly=backtest_real(data,replace(SMALL,cost_bps=10),"C_buy_hold")[0]
    assert costly.nav.iloc[-1]<free.nav.iloc[-1]
    reserve=backtest_real(data,SMALL,"G_buy_hold")[0]
    start=data.date.searchsorted(pd.Timestamp(SMALL.start))
    assert reserve.nav.iloc[-1]==pytest.approx(SMALL.initial_nav*data.G.iloc[-1]/data.G.iloc[start-1])
    assert reserve.fee.sum()==pytest.approx(0,abs=1e-8)
    assert real_metrics(reserve)["excess_sharpe"] is None


def test_censored_order_is_not_executed_at_a_fabricated_terminal_price():
    data=small_market(48)
    cfg=replace(SMALL,start=str(data.date.iloc[-2].date()),execution_delay=5)
    ledger,decisions,orders=backtest_real(data,cfg)
    assert orders.empty
    assert (decisions.status=="not_executed_end_of_snapshot").all()
    assert (ledger.weight_G==1).all()


def test_paired_intervals_are_deterministic_and_dates_must_align():
    data=small_market()
    a=backtest_real(data,SMALL)[0];b=backtest_real(data,SMALL,"risk_matched_static")[0]
    assert paired_inference(a,b,block=5,replications=100)==paired_inference(a,b,block=5,replications=100)
    same=paired_inference(a,a,block=5,replications=100)
    assert same["ci95_low"]==same["ci95_high"]==0
    with pytest.raises(ValueError):paired_inference(a,b.iloc[1:],block=5,replications=100)


def test_window_drawdown_counts_first_day_loss():
    data=small_market()
    ledger=backtest_real(data,SMALL)[0].iloc[:2].copy()
    ledger["return"]=[-.1,.05]
    assert real_metrics(ledger)["max_drawdown"]==pytest.approx(-.1)
