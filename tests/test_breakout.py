"""Known answers for transfer semantics, rather than assertions about profitability."""
from dataclasses import replace
import json
import numpy as np
import pandas as pd
import pytest
from strategy_lab.regimes.config import RegimeConfig
from strategy_lab.regimes.data import synthetic_prices
from strategy_lab.regimes.models import features,online_states
from strategy_lab.regimes.engine import targets,backtest
from strategy_lab.regimes.breakout.config import BreakoutConfig,names,protocol
from strategy_lab.regimes.breakout.data import synthetic_bars,validate_bars
from strategy_lab.regimes.breakout.signals import channel_signal,make_targets
from strategy_lab.regimes.breakout.research import run_account
from strategy_lab.regimes.breakout.report import primary_contrasts
from strategy_lab.regimes.breakout.reference import load_parent,sha256


def bars(close):
    c=np.asarray(close,float)
    return pd.DataFrame({"adjusted_open":c,"adjusted_high":c,"adjusted_low":c,"adjusted_close":c},
                        index=pd.bdate_range("2012-01-02",periods=len(c),name="date"))


def fixture():
    b=bars(np.r_[np.ones(55)*100,110,108,107,106,90,110])
    s=pd.DataFrame({"date":b.index[55:],"status":["ok","ok","cash_requested","ok","ok","ok"],
                    "weighted_state_log_return":[.01,-.01,.01,.01,.01,.01]})
    f=pd.DataFrame({"volatility":.3},index=b.index)
    return b,f,s


def test_shifted_channel_carry_exit_and_pulse_known_answer():
    b=bars([100,101,102,101,103,102,99,98]);a=channel_signal(b,2);p=channel_signal(b,2,True)
    np.testing.assert_array_equal(a.trend_state,[0,0,1,1,1,1,0,0])
    np.testing.assert_array_equal(p.trend_state,[0,0,1,0,1,0,0,0])
    assert a.upper.iloc[2]==101 and a.lower.iloc[2]==100


def test_current_high_low_excluded_but_current_close_observed():
    b=bars([100,101,102,103]);c=b.copy();c.loc[c.index[2],"adjusted_high"]=1000
    a=channel_signal(b,2);x=channel_signal(c,2)
    assert a.upper.iloc[2]==x.upper.iloc[2] and a.entry.iloc[2]==x.entry.iloc[2]
    assert x.upper.iloc[3]==1000


def test_equality_and_roundoff_are_not_breakouts():
    b=bars([100,100,100*(1+5e-13),101]);a=channel_signal(b,2)
    assert not a.entry.iloc[2] and a.entry.iloc[3]


@pytest.mark.parametrize("window",[True,1,0,2.5])
def test_invalid_window(window):
    with pytest.raises(ValueError):channel_signal(bars([1,2,3]),window)


def test_gate_recovery_reenters_carried_channel_and_failure_does_not_reset_latch():
    b,f,s=fixture();w,signals=make_targets(b,f,s)
    np.testing.assert_array_equal(w.channel55__breakout,[1,1,1,1,0,0])
    np.testing.assert_array_equal(w.channel55__hmm_breakout,[1,0,0,1,0,0])
    assert not signals[(signals.specification=="channel55")&(signals.date==s.date.iloc[3])].entry.iloc[0]
    np.testing.assert_array_equal(w.pulse55__breakout,[1,0,0,0,0,0])


def test_factorial_sizing_and_unchanged_control_targets():
    b,f,s=fixture();w,_=make_targets(b,f,s)
    np.testing.assert_array_equal(w.vol_hold,.5)
    for signal in ["channel55","channel20","channel100","pulse55"]:
        np.testing.assert_array_equal(w[signal+"__vol_breakout"],w[signal+"__breakout"]*.5)
        np.testing.assert_array_equal(w[signal+"__hmm_vol_breakout"],w[signal+"__hmm_breakout"]*.5)
    c=RegimeConfig();f2=features(b.adjusted_close,c);x,_=make_targets(b,f2,s)
    old=targets(f2,s,c)
    pd.testing.assert_frame_equal(x[["buy_hold","vol_hold"]],old[["buy_hold","vol_hold"]])


def test_zero_missing_or_extreme_volatility_requests_safe_sizing():
    b,f,s=fixture();f.loc[s.date,"volatility"]=[0,np.nan,.05,.15,.3,1.5]
    w,_=make_targets(b,f,s)
    np.testing.assert_allclose(w.vol_hold,[0,0,1,1,.5,.1])


def test_future_bars_cannot_change_past_channels_or_targets():
    rng=np.random.default_rng(31);b=bars(100*np.exp(np.cumsum(rng.normal(.001,.02,220))))
    changed=b.copy();changed.iloc[170:]*=np.linspace(2,4,50)[:,None]
    dates=b.index[100:];s=pd.DataFrame({"date":dates,"status":"ok","weighted_state_log_return":.001})
    a,_=make_targets(b,features(b.adjusted_close,RegimeConfig()),s)
    z,_=make_targets(changed,features(changed.adjusted_close,RegimeConfig()),s)
    pd.testing.assert_frame_equal(a.loc[:b.index[169]],z.loc[:b.index[169]])
    for window in [20,55,100]:
        pd.testing.assert_frame_equal(channel_signal(b,window).iloc[:170],channel_signal(changed,window).iloc[:170])


def test_actual_hmm_prefix_invariance_in_breakout_pipeline():
    # Short known-estimator test; production protocol stays at 756/21 and 3 states.
    rng=np.random.default_rng(33);b=bars(100*np.exp(np.cumsum(rng.normal(.0005,.01,190))))
    changed=b.copy();changed.iloc[165:]*=2
    cfg=replace(RegimeConfig(),train_window=60,volatility=5,tolerance=.01)
    f=features(b.adjusted_close,cfg);g=features(changed.adjusted_close,cfg)
    a,af,am=online_states(f,b.index[90],cfg);z,zf,zm=online_states(g,b.index[90],cfg)
    cut=b.index[165]
    pd.testing.assert_frame_equal(a[a.date<cut],z[z.date<cut])
    pd.testing.assert_frame_equal(af[af.decision_date<str(cut.date())],zf[zf.decision_date<str(cut.date())])
    assert am and [m for m in am if m['decision_date']<str(cut.date())]==[m for m in zm if m['decision_date']<str(cut.date())]
    w,_=make_targets(b,f,a);v,_=make_targets(changed,g,z)
    pd.testing.assert_frame_equal(w.loc[:b.index[164]],v.loc[:b.index[164]])


def test_next_close_initial_fee_drift_and_cash_conservation():
    b=bars([100,110,121,100,115]);w=pd.Series([.5,.5,0,1,0],index=b.index)
    l,d,t=run_account(b.adjusted_close,w,"channel55__hmm_vol_breakout",10,.03)
    assert l.units.iloc[0]==0 and l.security_pnl.iloc[1]==0
    assert t.execution_date.iloc[0]==str(b.index[1].date()) and t.fee.iloc[0]>0
    assert t.signed_notional.iloc[1]<0  # rebalance drift at unchanged 50% target
    np.testing.assert_allclose(l.nav,l.cash+l.units*l.model_unit_price,atol=1e-8)
    np.testing.assert_allclose(l.nav-l.prior_nav,l.security_pnl+l.cash_interest-l.fee,atol=1e-8)
    assert (l.cash>=0).all() and d.status.iloc[-1]=="not_executed_end_of_snapshot"


@pytest.mark.parametrize("strategy",["buy_hold","vol_hold"])
def test_transfer_preserves_parent_control_accounts(strategy):
    b=bars([100,105,99,110]);w=pd.Series([1,.5,0,1],index=b.index)
    got=run_account(b.adjusted_close,w,strategy,5,0)
    expected=backtest(b.adjusted_close,w,RegimeConfig(),"buy_hold" if strategy=="buy_hold" else "vol_hold",5,0)
    for a,z in zip(got,expected):pd.testing.assert_frame_equal(a,z)


def test_unknown_account_rejected():
    b=bars([1,2,3])
    with pytest.raises(ValueError):run_account(b.adjusted_close,pd.Series(1,index=b.index),"unknown")


def test_invented_envelopes_preserve_parent_closes_and_validate():
    d=synthetic_bars();pd.testing.assert_frame_equal(d[["date","ticker","adjusted_close"]],synthetic_prices())
    assert d.adjusted_high.ge(d.adjusted_close).all() and d.adjusted_low.le(d.adjusted_close).all()
    pd.testing.assert_frame_equal(d,validate_bars(d,d.date.drop_duplicates()))


@pytest.mark.parametrize("kind",["high","low","nan","negative","duplicate","missing","order"])
def test_reject_invalid_bars(kind):
    d=synthetic_bars().iloc[:10].copy()
    if kind=="high":d.loc[0,"adjusted_high"]=1
    if kind=="low":d.loc[0,"adjusted_low"]=1e6
    if kind=="nan":d.loc[0,"adjusted_open"]=np.nan
    if kind=="negative":d.loc[0,"adjusted_open"]=-1
    if kind=="duplicate":d=pd.concat([d,d.iloc[[0]]])
    if kind=="missing":d=d.iloc[1:]
    if kind=="order":d=d.iloc[::-1]
    with pytest.raises(ValueError):validate_bars(d)


def test_predeclared_protocol_has_full_factorial_and_unchanged_parent():
    p=protocol();assert len(names())==18 and len(set(names()))==18
    assert p["hmm_config"]==RegimeConfig().to_dict() and len(p["comparisons"])==5
    assert p["hmm_features"]==["log_return","volatility"]
    assert p["signal_specifications"][-1]=={"name":"pulse55","window":55,"pulse":True}
    with pytest.raises(ValueError):replace(BreakoutConfig(),primary_window=20).validate()


def test_interaction_is_difference_in_differences_with_exposure():
    values={"breakout":(.01,1),"vol_breakout":(.008,.8),"hmm_breakout":(.006,.5),"hmm_vol_breakout":(.005,.4)}
    ledgers={"channel55__"+k:pd.DataFrame({"return":[r,r],"held_weight":[w,w]}) for k,(r,w) in values.items()}
    contrasts=list(primary_contrasts(ledgers));assert len(contrasts)==5
    np.testing.assert_allclose(contrasts[-1][1],.001);np.testing.assert_allclose(contrasts[-1][2],.1)


def test_parent_receipt_rejects_different_protocol(tmp_path):
    (tmp_path/"manifest.json").write_text(json.dumps({"data_kind":"synthetic"}))
    (tmp_path/"protocol.json").write_text(json.dumps({"config":{}}))
    with pytest.raises(ValueError,match="configuration"):load_parent(tmp_path,"synthetic")
