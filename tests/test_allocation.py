"""Known-answer BL/risk budgets, optimality, temporal boundaries and funding."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from strategy_lab.allocation.config import AllocationConfig,ASSETS,METHODS,variants
from strategy_lab.allocation.models import (allocate,black_litterman,estimate,risk_contributions,
                                           linear_minimum,checked_covariance)
from strategy_lab.allocation.engine import funded_rebalance,backtest,metrics
from strategy_lab.allocation.data import validate_prices
from strategy_lab.allocation.research import make_targets


def market(n=340):
    rng=np.random.default_rng(71);r=rng.normal(.0002,.009,(n,5))
    return pd.DataFrame(100*np.exp(np.cumsum(r,axis=0)),index=pd.bdate_range("2010-01-04",periods=n),columns=ASSETS)


def covariance():
    return pd.DataFrame(np.diag([.04,.09,.01,.06,.08]),index=ASSETS,columns=ASSETS)


def test_bl_diagonal_closed_form_and_confidence_zero():
    cov=covariance();prior=pd.Series([.03,.04,.02,.05,.03],index=ASSETS)
    q=np.array([.12,-.03,.04,.01,.07])
    views=[{'picks':{a:1.},'annual_return':v} for a,v in zip(ASSETS,q)]
    mean,uncertainty=black_litterman(cov,prior,views,.25,.05)
    np.testing.assert_allclose(mean,.75*prior+.25*q,atol=1e-14)
    np.testing.assert_allclose(np.diag(uncertainty),.05*.75*np.diag(cov))
    none,_=black_litterman(cov,prior,views,0.)
    pd.testing.assert_series_equal(none,prior)


def test_named_relative_view_matches_precision_formula_and_asset_permutation():
    cov=covariance();prior=pd.Series(.05,index=ASSETS)
    views=[{'picks':{'SPY':1.,'EFA':-1.},'annual_return':.02}]
    mean,uncertainty=black_litterman(cov,prior,views,.5,.05)
    p=np.array([[1.,-1.,0,0,0]]);c=.05*cov.to_numpy();omega=np.diag(np.diag(p@c@p.T))
    precision=np.linalg.inv(c)+p.T@np.linalg.inv(omega)@p
    expected=np.linalg.solve(precision,np.linalg.solve(c,prior)+p.T@np.linalg.solve(omega,np.array([.02])))
    np.testing.assert_allclose(mean,expected,atol=1e-14)
    order=list(reversed(ASSETS));permuted,_=black_litterman(cov.loc[order,order],prior,views,.5,.05)
    np.testing.assert_allclose(permuted.reindex(ASSETS),mean,atol=1e-14)
    assert np.linalg.eigvalsh(uncertainty).min()>=-1e-14
    with pytest.raises(ValueError):black_litterman(cov,prior,[{'picks':{'UNKNOWN':1},'annual_return':.1}])


def test_bl_tau_cancels_with_proportional_view_uncertainty():
    cov=covariance();prior=pd.Series(.03,index=ASSETS);views=[{'picks':{'SPY':1},'annual_return':.15}]
    a,_=black_litterman(cov,prior,views,.5,.01);b,_=black_litterman(cov,prior,views,.5,.3)
    np.testing.assert_allclose(a,b,atol=1e-14)


def test_zero_confidence_reference_prior_reproduces_equal_weight_utility_optimum():
    mean=pd.Series([.2,-.1,.03,.08,.02],index=ASSETS)
    solution=allocate(mean,covariance(),'black_litterman',replace(AllocationConfig(),confidence=0.))
    np.testing.assert_allclose(solution.weights,np.ones(5)/5,atol=1e-10)


def test_minimum_variance_ignores_mean_but_bl_utility_responds():
    cov=covariance();a=pd.Series(.02,index=ASSETS);b=a.copy();b['SPY']=.4
    cfg=AllocationConfig()
    np.testing.assert_array_equal(allocate(a,cov,'min_variance',cfg).weights,allocate(b,cov,'min_variance',cfg).weights)
    first=allocate(a,cov,'black_litterman',cfg);second=allocate(b,cov,'black_litterman',cfg)
    assert second.weights['SPY']>first.weights['SPY']+.05


def test_diagonal_risk_budget_matches_inverse_volatility_without_binding_caps():
    cov=covariance();mean=pd.Series(.03,index=ASSETS)
    cfg=replace(AllocationConfig(),weight_cap=1.)
    result=allocate(mean,cov,'risk_budget',cfg)
    expected=1/np.sqrt(np.diag(cov));expected/=expected.sum()
    np.testing.assert_allclose(result.weights,expected,atol=1e-6)
    _,fractions=risk_contributions(result.weights,cov)
    np.testing.assert_allclose(fractions,np.ones(5)/5,atol=1e-6)


def test_capped_budget_does_not_claim_exact_parity_when_cap_binds():
    cov=pd.DataFrame(np.diag([.00001,.04,.04,.04,.04]),index=ASSETS,columns=ASSETS)
    result=allocate(pd.Series(.03,index=ASSETS),cov,'risk_budget')
    assert result.weights.max()<=.4+1e-8
    assert result.diagnostics['risk_fraction_l2']>.1
    assert result.diagnostics['optimality_residual']<2e-5


def test_return_tilt_zero_equals_risk_budget_and_normalization_is_unit_invariant():
    cov=covariance();mean=pd.Series([.1,-.03,.01,.06,.05],index=ASSETS)
    a=allocate(mean,cov,'risk_budget');b=allocate(mean,cov,'return_tilted_budget',replace(AllocationConfig(),tilt=0.))
    np.testing.assert_array_equal(a.weights,b.weights)
    c=allocate(mean,cov,'return_tilted_budget');d=allocate(mean*100,cov*10000,'return_tilted_budget')
    np.testing.assert_allclose(c.weights,d.weights,atol=1e-8)


def test_risk_contributions_sum_to_volatility_and_fraction_one():
    cov=covariance();w=np.array([.1,.2,.3,.2,.2])
    absolute,fraction=risk_contributions(w,cov)
    assert absolute.sum()==pytest.approx(np.sqrt(w@cov.to_numpy()@w))
    assert fraction.sum()==pytest.approx(1.)
    assert not np.allclose(fraction,np.ones(5)/5)


@pytest.mark.parametrize('method',METHODS)
def test_every_method_obeys_constraints_and_label_alignment(method):
    cov=covariance();mean=pd.Series([.1,.03,.01,.05,.04],index=ASSETS)
    a=allocate(mean,cov,method)
    assert a.weights.sum()==pytest.approx(1.)
    assert a.weights.min()>=0 and a.weights.max()<=.4+1e-8
    order=list(reversed(ASSETS));b=allocate(mean,cov.loc[order,order],method)
    np.testing.assert_allclose(a.weights,b.weights.reindex(ASSETS),atol=2e-6)


def test_solver_success_flag_cannot_override_infeasible_solution(monkeypatch):
    import strategy_lab.allocation.models as models
    monkeypatch.setattr(models,'minimize',lambda *a,**k:SimpleNamespace(x=np.array([1.,0,0,0,0]),success=True,nit=1,message='fake success'))
    with pytest.raises(FloatingPointError):allocate(pd.Series(.03,index=ASSETS),covariance(),'min_variance')


def test_failed_solver_is_not_reported_as_success(monkeypatch):
    import strategy_lab.allocation.models as models
    monkeypatch.setattr(models,'minimize',lambda *a,**k:SimpleNamespace(x=np.ones(5)/5,success=False,nit=1,message='iteration limit'))
    with pytest.raises(FloatingPointError,match='iteration limit'):allocate(pd.Series(.03,index=ASSETS),covariance(),'min_variance')


def test_quadratic_optimum_certificate_has_known_linear_minimum():
    g=np.array([3.,1.,2.,4.,5.]);v=linear_minimum(g,.4)
    np.testing.assert_allclose(v,[.2,.4,.4,0,0],atol=1e-15)


def test_estimator_uses_only_supplied_training_window_and_records_shrinkage():
    prices=market();r=prices.pct_change(fill_method=None).iloc[1:41]
    cfg=replace(AllocationConfig(),lookback=40)
    mean,cov,shrink=estimate(r,cfg)
    np.testing.assert_allclose(mean,r.mean()*252)
    assert 0<=shrink<=1 and np.linalg.eigvalsh(cov).min()>0
    with pytest.raises(ValueError):estimate(r.iloc[:10],cfg)


def test_future_prices_do_not_rewrite_targets_parameters_or_events():
    p=market();q=p.copy();q.iloc[320:]*=np.linspace(1.4,2.,len(q)-320)[:,None]
    cfg=replace(AllocationConfig(),lookback=40)
    start=p.index[270];cut=p.index[320]
    a,ae,ap,_=make_targets(p,cfg,start,perturb=False)
    b,be,bp,_=make_targets(q,cfg,start,perturb=False)
    for name in a:pd.testing.assert_frame_equal(a[name].loc[a[name].index<cut],b[name].loc[b[name].index<cut])
    pd.testing.assert_frame_equal(ae[ae.decision_date<str(cut.date())],be[be.decision_date<str(cut.date())])
    assert [x for x in ap if x['decision_date']<str(cut.date())]==[x for x in bp if x['decision_date']<str(cut.date())]
    assert len(a)==23


def test_failed_method_requests_cash_without_removing_evaluation_dates(monkeypatch):
    import strategy_lab.allocation.research as research
    original=research.allocate
    def failing(mean,cov,method,*args):
        if method=='black_litterman':raise FloatingPointError('deliberate failure')
        return original(mean,cov,method,*args)
    monkeypatch.setattr(research,'allocate',failing)
    p=market(285);cfg=replace(AllocationConfig(),lookback=40)
    tables,events,_,_=make_targets(p,cfg,p.index[270],perturb=False)
    assert tables['black_litterman'].to_numpy().sum()==0
    assert events[events.method.eq('black_litterman')].status.eq('cash_requested').all()
    assert events[events.method.eq('equal_weight')].status.eq('ok').all()


def test_controlled_mean_shocks_leave_mean_independent_methods_unchanged():
    p=market(285);cfg=replace(AllocationConfig(),lookback=40,perturbations=2)
    _,_,_,shocks=make_targets(p,cfg,p.index[270],perturb=True)
    independent=shocks[shocks.method.isin(['equal_weight','min_variance','risk_budget'])]
    assert independent.status.eq('ok').all()
    assert independent.sleeve_half_l1.eq(0).all()
    assert shocks[shocks.method.eq('mean_variance')].sleeve_half_l1.max()>0


def test_first_fee_and_next_close_execution_known_answer():
    dates=pd.bdate_range('2021-01-04',periods=4)
    prices=pd.DataFrame({'A':[100.,200.,220.,220.],'B':[100.,100.,100.,100.]},index=dates)
    target=pd.DataFrame({'A':[1.],'B':[0.]},index=dates[:1])
    ledger,decisions,trades=backtest(prices,target,cost_bps=10)
    assert ledger.nav.iloc[0]==100000
    assert ledger.security_pnl.iloc[1]==0
    assert ledger.nav.iloc[1]==pytest.approx(100000/1.001)
    assert ledger.nav.iloc[2]==pytest.approx(100000/1.001*1.1)
    assert trades.execution_date.iloc[0]==str(dates[1].date())
    assert trades.decision_date.iloc[0]==str(dates[0].date())


def test_mixed_rebalance_fees_cash_and_after_fee_target_known_identity():
    u,c,d,f=funded_rebalance([500.,0.],50000.,[200.,100.],[.3,.5],10)
    nav=float(u@np.array([200.,100.])+c)
    assert nav+f.sum()==pytest.approx(150000.,abs=1e-7)
    np.testing.assert_allclose(u*np.array([200.,100.])/nav,[.3,.5],atol=1e-12)
    assert c/nav==pytest.approx(.2)
    assert d[0]<0<d[1] and (f>0).all()


def test_drift_creates_turnover_even_when_requested_weights_are_unchanged():
    dates=pd.bdate_range('2021-01-04',periods=4)
    p=pd.DataFrame({'A':[100.,100.,200.,200.],'B':[100.]*4},index=dates)
    target=pd.DataFrame({'A':[.5,.5],'B':[.5,.5]},index=dates[[0,2]])
    ledger,_,trades=backtest(p,target,cost_bps=5)
    assert ledger.turnover.iloc[3]>0
    assert (trades[trades.execution_date==str(dates[3].date())].signed_notional!=0).all()


def test_independent_final_cash_and_unit_sums_reconstruct_account():
    p=market(80);target=pd.DataFrame(.1,index=p.index[::7],columns=ASSETS)
    ledger,decisions,trades=backtest(p,target,cost_bps=10,cash_rate=.03)
    cash=100000+ledger.cash_interest.sum()-trades.signed_notional.sum()-trades.fee.sum()
    units=trades.groupby('ticker').quantity.sum().reindex(ASSETS,fill_value=0).to_numpy()
    assert ledger.cash.iloc[-1]==pytest.approx(cash,abs=1e-7)
    assert ledger.nav.iloc[-1]==pytest.approx(cash+units@p.iloc[-1].to_numpy(),abs=1e-7)
    assert ledger.cash.min()>=0 and ledger.bridge_error.abs().max()<1e-7
    assert ledger.date.tolist()==p.index.strftime('%Y-%m-%d').tolist()


def test_annualized_excess_sharpe_uses_arithmetic_mean_and_cash_reference():
    p=market(80);target=pd.DataFrame(.1,index=p.index[::7],columns=ASSETS)
    ledger,_,_=backtest(p,target,cash_rate=.03)
    m=metrics(ledger);excess=ledger['return']-ledger.cash_return
    assert m['excess_sharpe']==pytest.approx(excess.mean()/excess.std(ddof=1)*np.sqrt(252))


@pytest.mark.parametrize('mutation',['duplicate','missing_asset','missing_session','negative','unordered'])
def test_invalid_input_fails_without_shortening_history(mutation):
    dates=pd.bdate_range('2020-01-01',periods=5)
    d=pd.DataFrame([{'date':date,'ticker':asset,'adjusted_close':100.} for date in dates for asset in sorted(ASSETS)])
    if mutation=='duplicate':d=pd.concat([d,d.iloc[:1]],ignore_index=True)
    if mutation=='missing_asset':d=d.iloc[1:]
    if mutation=='missing_session':d=d[d.date!=dates[2]]
    if mutation=='negative':d.loc[0,'adjusted_close']=-1
    if mutation=='unordered':d=d.iloc[::-1]
    with pytest.raises(ValueError):validate_prices(d,dates)


def test_invalid_config_and_singular_covariance_rejected():
    with pytest.raises(ValueError):replace(AllocationConfig(),weight_cap=.1).validate()
    with pytest.raises(ValueError):replace(AllocationConfig(),confidence=1.).validate()
    with pytest.raises(ValueError):checked_covariance(pd.DataFrame(np.ones((5,5)),index=ASSETS,columns=ASSETS))
