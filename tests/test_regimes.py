"""Independent known answers for filtering, timing, funding and causality."""
from dataclasses import replace
import itertools
import numpy as np
import pandas as pd
import pytest
from strategy_lab.regimes.config import RegimeConfig, STRATEGIES
from strategy_lab.regimes.data import validate_prices
from strategy_lab.regimes.models import (FittedHMM, features, fit_hmm, forward_step,
                                        online_states, smooth_log_index, steady_gain)
from strategy_lab.regimes.engine import backtest, funded_trade, metrics, paired_interval, targets


def small_prices(n=160):
    rng = np.random.default_rng(71)
    return pd.Series(100*np.exp(np.cumsum(rng.normal(.0003, .009, n))),
                     index=pd.bdate_range("2021-01-04", periods=n))


def fixed_model(observations, cfg):
    return FittedHMM(np.array([0., 0.]), np.array([1., 1.]), np.array([.2, .5, .3]),
                     np.array([[.8,.15,.05],[.1,.8,.1],[.05,.15,.8]]),
                     np.array([[-.01,.1],[0.,.15],[.01,.2]]), np.ones((3,2))*.01,
                     np.array([-.01,0.,.01]), 5, .0001, [])


def test_forward_matches_exhaustive_state_path_enumeration():
    transition = np.array([[.8,.2],[.3,.7]])
    start = np.array([.6,.4])
    emissions = np.array([[.7,.2],[.3,.6],[.5,.4]])
    probability = None
    for t in range(len(emissions)):
        probability = forward_step(np.log(emissions[t]), transition, probability, start)
        mass = np.zeros(2)
        for path in itertools.product(range(2), repeat=t+1):
            p = start[path[0]]*emissions[0,path[0]]
            for i in range(1,t+1):
                p *= transition[path[i-1],path[i]]*emissions[i,path[i]]
            mass[path[-1]] += p
        np.testing.assert_allclose(probability, mass/mass.sum(), rtol=1e-13)


def test_filter_retains_history_and_handles_tiny_likelihoods():
    a = np.array([[.99,.01],[.01,.99]])
    previous = np.array([.99,.01]); start = np.array([.1,.9])
    continuous = forward_step(np.array([-10000.,-10000.]), a, previous, start)
    restarted = forward_step(np.array([-10000.,-10000.]), a, None, start)
    assert continuous[0] > .9 and restarted[0] == pytest.approx(.1)


def test_kalman_matches_hand_update_and_converges_to_matched_ema():
    q,r = 1e-5,.001
    values = np.linspace(0,1,200)+.01*np.sin(np.arange(200))
    kalman,ema = smooth_log_index(values,q,r)
    k1 = (1+q)/(1+q+r)
    assert kalman[1] == pytest.approx(values[0]+k1*(values[1]-values[0]))
    gain = steady_gain(q,r)
    assert ema[1] == pytest.approx(values[0]+gain*(values[1]-values[0]))
    np.testing.assert_allclose(kalman[-20:],ema[-20:],atol=1e-8)
    flat_k,flat_e = smooth_log_index(np.ones(30),q,r)
    np.testing.assert_array_equal(flat_k,flat_e)


def test_future_changes_do_not_rewrite_features_states_fits_or_targets():
    cfg = replace(RegimeConfig(), train_window=40, refit_every=13, volatility=5, momentum=5)
    prices = small_prices(); changed = prices.copy(); changed.iloc[125:] *= np.linspace(1.5,3,35)
    start = prices.index[50]; cut = prices.index[125]
    fa = features(prices,cfg); fb = features(changed,cfg)
    a,af,am = online_states(fa,start,cfg,fixed_model)
    b,bf,bm = online_states(fb,start,cfg,fixed_model)
    pd.testing.assert_frame_equal(fa.loc[:prices.index[124]],fb.loc[:prices.index[124]])
    pd.testing.assert_frame_equal(a[a.date<cut],b[b.date<cut])
    pd.testing.assert_frame_equal(af[af.decision_date<str(cut.date())],bf[bf.decision_date<str(cut.date())])
    assert [m for m in am if m['decision_date']<str(cut.date())] == [m for m in bm if m['decision_date']<str(cut.date())]
    pd.testing.assert_frame_equal(targets(fa,a,cfg).loc[:prices.index[124]],targets(fb,b,cfg).loc[:prices.index[124]])


def test_refit_excludes_today_and_refilters_training_tail():
    cfg = replace(RegimeConfig(),train_window=30,refit_every=10,volatility=5,momentum=5)
    prices = small_prices(80); f = features(prices,cfg); seen=[]
    def spy(x,c):
        seen.append(x.copy()); return fixed_model(x,c)
    states,fits,snapshots = online_states(f,prices.index[40],cfg,spy)
    np.testing.assert_array_equal(seen[0],f[["log_return","volatility"]].iloc[10:40].to_numpy())
    assert fits.train_end.iloc[0] == str(prices.index[39].date())
    model = fixed_model(seen[0],cfg); probability=None
    for x in seen[0]: probability=model.step(x,probability)
    np.testing.assert_allclose(snapshots[0]["training_tail_probability"],probability)
    probability=model.step(f[["log_return","volatility"]].iloc[40],probability)
    np.testing.assert_allclose(states[["p_0","p_1","p_2"]].iloc[0],probability)
    assert len(seen) == 4


def test_failure_requests_cash_until_next_scheduled_refit():
    cfg=replace(RegimeConfig(),train_window=30,refit_every=10,volatility=5,momentum=5)
    f=features(small_prices(80),cfg); count=0
    def fail_once(x,c):
        nonlocal count
        count+=1
        if count==1: raise FloatingPointError("deliberate known failure")
        return fixed_model(x,c)
    states,fits,_=online_states(f,f.index[40],cfg,fail_once)
    assert states.status.iloc[:10].eq("cash_requested").all()
    assert states.status.iloc[10:].eq("ok").all()
    assert "deliberate" in fits.reason.iloc[0]
    assert targets(f,states,cfg).kalman_hmm.iloc[:10].eq(0).all()


def test_real_hmm_training_is_reproducible_and_future_blind():
    cfg=replace(RegimeConfig(),train_window=80,max_iterations=300,tolerance=.01)
    rng=np.random.default_rng(13)
    # Separated alternating states exercise EM and the actual scaling path.
    regimes=np.repeat(np.arange(3),[27,27,26])
    x=np.column_stack([regimes*.01+rng.normal(0,.001,80),regimes*.1+rng.normal(0,.01,80)])
    a=fit_hmm(x,cfg); b=fit_hmm(x,cfg)
    np.testing.assert_array_equal(a.means,b.means)
    np.testing.assert_allclose(a.center,x.mean(axis=0))
    np.testing.assert_allclose(a.scale,x.std(axis=0,ddof=0))
    assert np.diff(a.raw_return_means).min() >= 0
    with pytest.raises(ValueError): fit_hmm(np.ones((80,2)),cfg)


def test_actual_estimator_prefix_invariance_across_refits():
    cfg=replace(RegimeConfig(),train_window=60,refit_every=21,volatility=5,momentum=5,tolerance=.01)
    prices=small_prices(150);changed=prices.copy();changed.iloc[130:]*=2
    f=features(prices,cfg);g=features(changed,cfg)
    a,af,am=online_states(f,prices.index[70],cfg)
    b,bf,bm=online_states(g,prices.index[70],cfg)
    cut=prices.index[130]
    assert am, "At least one real estimator fit must succeed"
    pd.testing.assert_frame_equal(a[a.date<cut],b[b.date<cut])
    pd.testing.assert_frame_equal(af[af.decision_date<str(cut.date())],bf[bf.decision_date<str(cut.date())])
    assert [m for m in am if m['decision_date']<str(cut.date())] == [m for m in bm if m['decision_date']<str(cut.date())]


def test_next_close_delay_and_first_purchase_fee_known_answer():
    cfg=RegimeConfig(); dates=pd.bdate_range("2021-01-04",periods=4)
    price=pd.Series([100.,200.,220.,220.],index=dates)
    weight=pd.Series(1.,index=dates)
    ledger,decisions,trades=backtest(price,weight,cfg,"buy_hold",10)
    assert ledger.nav.iloc[0] == 100000
    assert ledger.security_pnl.iloc[1] == 0 # 100 -> 200 happened before entry.
    expected=100000/1.001
    assert ledger.nav.iloc[1] == pytest.approx(expected)
    assert ledger.nav.iloc[2] == pytest.approx(expected*1.1)
    assert trades.execution_date.iloc[0] == str(dates[1].date())
    assert decisions.decision_date.iloc[0] == str(dates[0].date())
    assert trades.fee.iloc[0] == pytest.approx(100000-expected)


def test_trade_uses_drifted_holdings_and_exact_funding():
    # A previous 50/50 account has drifted to 2/3 risky after price doubles.
    units,cash,delta,fee=funded_trade(500.,50000.,200.,.5,10)
    assert delta < 0 and fee > 0
    nav=units*200+cash
    assert units*200/nav == pytest.approx(.5)
    assert nav+fee == pytest.approx(150000.)
    u,c,delta,fee=funded_trade(units,cash,200.,0.,10)
    assert u == 0 and c == pytest.approx(nav-fee)


def test_independent_trade_cash_flows_reconcile_and_dates_match_all_methods():
    cfg=RegimeConfig(); price=small_prices(100)
    weight=pd.Series(np.tile([0.,.5,1.,.7],25),index=price.index)
    for strategy in STRATEGIES:
        ledger,decisions,trades=backtest(price,weight,cfg,strategy,10,.03)
        assert ledger.date.tolist() == price.index.strftime("%Y-%m-%d").tolist()
        external_cash=cfg.initial_nav+ledger.cash_interest.sum()-trades.signed_notional.sum()-trades.fee.sum()
        assert ledger.cash.iloc[-1] == pytest.approx(external_cash,abs=1e-7)
        assert ledger.units.iloc[-1] == pytest.approx(trades.quantity.sum(),abs=1e-10)
        assert ledger.nav.iloc[-1] == pytest.approx(external_cash+trades.quantity.sum()*price.iloc[-1],abs=1e-7)
        assert ledger.bridge_error.abs().max() < 1e-7
        assert ledger.cash.min() >= 0
        if strategy != "buy_hold":
            assert decisions.status.iloc[-1] == "not_executed_end_of_snapshot"


def test_mutating_later_execution_price_does_not_change_frozen_target():
    price=small_prices(20); weights=pd.Series(.6,index=price.index)
    a,ad,at=backtest(price,weights,RegimeConfig(),"raw_momentum",5)
    changed=price.copy();changed.iloc[1:]*=2
    b,bd,bt=backtest(changed,weights,RegimeConfig(),"raw_momentum",5)
    pd.testing.assert_frame_equal(ad,bd)
    assert bt.quantity.iloc[0] == pytest.approx(at.quantity.iloc[0]/2)
    pd.testing.assert_frame_equal(a.iloc[:1],b.iloc[:1])


def test_metrics_use_arithmetic_excess_sharpe_and_initial_wealth_for_drawdown():
    d=pd.DataFrame({"return":[-.1,.2],"cash_return":[.001,.002],"turnover":[1.,0.],
                    "held_weight":[0.,1.],"end_weight":[1.,1.],"fee":[1.,0.],
                    "cash":[0.,0.],"bridge_error":[0.,0.]})
    actual=metrics(d);excess=np.array([-.101,.198])
    assert actual['excess_sharpe'] == pytest.approx(excess.mean()/excess.std(ddof=1)*np.sqrt(252))
    assert actual['max_drawdown'] == pytest.approx(-.1)
    interval=paired_interval(np.full(100,.001),20,100)
    assert interval['lower_95'] == pytest.approx(.252)
    assert interval['upper_95'] == pytest.approx(.252)


@pytest.mark.parametrize("mutation",["duplicate","missing_asset","missing_session","negative","unordered","nan"])
def test_input_rejects_invalid_prices_and_missing_sessions(mutation):
    dates=pd.bdate_range("2020-01-01",periods=5)
    d=pd.DataFrame([{'date':date,'ticker':asset,'adjusted_close':100.} for date in dates for asset in ('QQQ','SPY')])
    if mutation=='duplicate':d=pd.concat([d,d.iloc[:1]],ignore_index=True)
    if mutation=='missing_asset':d=d.iloc[1:]
    if mutation=='missing_session':d=d[d.date!=dates[2]]
    if mutation=='negative':d.loc[0,'adjusted_close']=-1
    if mutation=='unordered':d=d.iloc[::-1]
    if mutation=='nan':d.loc[0,'adjusted_close']=np.nan
    with pytest.raises(ValueError): validate_prices(d,dates)


def test_config_and_probability_validation():
    with pytest.raises(ValueError):replace(RegimeConfig(),refit_every=0).validate()
    with pytest.raises(ValueError):replace(RegimeConfig(),target_vol=float('nan')).validate()
    with pytest.raises(ValueError):forward_step(np.zeros(2),np.ones((2,2)),None,np.array([.5,.5]))
