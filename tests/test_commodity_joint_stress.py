"""Adverse reference overlays have a causal clock and one cash effect."""
from copy import deepcopy
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol,run_research
from strategy_lab.commodities.research_fixture import research_frames
from strategy_lab.commodities.joint_stress import CASES,anchor_legs,compile_joint_stress


@pytest.fixture(scope='module')
def setup():
    tape=prepare(*research_frames())
    day=tape.dates.get_loc('2021-01-04')
    keys=tape.contracts.contract.iloc[tape.pairs[day,0]].tolist()
    p=ResearchProtocol(start='2021-01-04',end='2021-02-05',execution_policy='staged',exit_lead=10,entry_budget=True)
    cohorts=pd.DataFrame([dict(entry_session=p.start,product='WTI',contracts=';'.join(keys))])
    tape=deepcopy(tape)
    for score in tape.updates.values():score['bm_spread_near_direction']=1
    baseline=run_research(tape,'bm_spread',p)
    legs=anchor_legs(tape,cohorts,baseline['trades'],True)
    return tape,p,cohorts,legs,day


def test_fixed_leg_sign_usd_anchor_step_and_no_automatic_rebound(setup):
    tape,p,c,legs,day=setup
    s=compile_joint_stress(tape,c,legs,CASES[6])
    for r in legs.itertuples(index=False):
        k=tape.contracts.index[tape.contracts.contract.eq(r.contract)][0]
        shift=-np.sign(r.baseline_quantity)*.05*r.anchor_usd_per_unit
        np.testing.assert_allclose(s.price_reference[:day+1,k],tape.prices[:day+1,k],equal_nan=True)
        valid=np.isfinite(tape.prices[day+1:,k])
        np.testing.assert_allclose((s.price_reference[day+1:,k]-tape.prices[day+1:,k])[valid],shift)
        assert shift*r.baseline_quantity<0
    assert s.margin_factor[day+11]==1
    assert s.price_events.hypothetical_full_baseline_leg_impulse.lt(0).all()


def test_current_eod_price_surprise_does_not_change_morning_request(setup):
    tape,p,c,legs,day=setup
    a=compile_joint_stress(tape,c,legs,CASES[7]);b=compile_joint_stress(tape,c,legs,CASES[8])
    config=replace(p,end='2021-01-05')
    x=run_research(tape,'bm_spread',config,stress=a);y=run_research(tape,'bm_spread',config,stress=b)
    pd.testing.assert_frame_equal(x['entry_admissions'],y['entry_admissions'])
    pd.testing.assert_frame_equal(x['decisions'],y['decisions'])
    assert x['ledger'].equity.iloc[-1]!=y['ledger'].equity.iloc[-1]


def test_missing_and_negative_reference_prices_are_not_filled_or_clipped(setup):
    tape,p,c,legs,day=setup
    changed=deepcopy(tape);k=changed.pairs[day,0,0]
    changed.prices[day+1,k]=.001
    changed.prices[day+2,k]=np.nan
    s=compile_joint_stress(changed,c,legs,CASES[-1])
    assert s.price_reference[day+1,k]<0 and np.isnan(s.price_reference[day+2,k])


def test_overlapping_price_impulses_add_without_compounding_margins(setup):
    tape,p,c,legs,day=setup
    extra=c.assign(entry_session='2021-01-05')
    second=legs.copy();second['entry_session']='2021-01-05'
    obs=day-1;second['observation']=str(tape.dates[obs].date());second['anchor_session']=str(tape.dates[obs].date())
    second['anchor_usd_per_unit']=[abs(tape.prices[obs,tape.contracts.index[tape.contracts.contract.eq(k)][0]]) for k in second.contract]
    s=compile_joint_stress(tape,pd.concat([c,extra]),pd.concat([legs,second]),CASES[-1])
    k=tape.pairs[day,0,0]
    expected=float(s.price_events[s.price_events.contract.eq(tape.contracts.contract.iloc[k])].usd_per_unit_step.sum())
    assert np.isclose(s.price_reference[day+2,k]-tape.prices[day+2,k],expected)
    assert s.margin_factor[day+2]==4


def test_future_overlay_perturbation_cannot_rewrite_prior_cash(setup):
    tape,p,c,legs,day=setup
    s=compile_joint_stress(tape,c,legs,CASES[-1]);other=deepcopy(s)
    other.price_reference[day+3:]-=1000
    config=replace(p,end='2021-01-06')
    a=run_research(tape,'bm_spread',config,stress=s);b=run_research(tape,'bm_spread',config,stress=other)
    for name in ['ledger','trades','entry_admissions','stress_sessions']:
        pd.testing.assert_frame_equal(a[name],b[name])


def test_shocked_terminal_marks_and_vm_reconcile_without_double_debit(setup):
    tape,p,c,legs,day=setup
    s=compile_joint_stress(tape,c,legs,CASES[7])
    r=run_research(tape,'bm_spread',replace(p,end='2021-01-05'),stress=s)
    ledger=r['ledger']
    np.testing.assert_allclose(ledger.equity,ledger.opening_equity+ledger.variation_margin-ledger.costs,atol=1e-8)
    np.testing.assert_allclose(ledger.free_cash,ledger.equity-ledger.reserve,atol=1e-8)
    assert abs(r['reconciliation']['terminal_error'])<1e-6
    # Wrongly mixing original-price terminal marks with shocked fills must fail.
    held=r['holdings'].query("session == '2021-01-05'")
    original=sum(h.quantity*h.multiplier*tape.prices[day+1,tape.contracts.index[tape.contracts.contract.eq(h.contract)][0]] for h in held.itertuples(index=False))
    bridge=p.capital-(r['trades'].delta*r['trades'].reference*r['trades'].multiplier).sum()+original-r['trades'].cost.sum()
    assert abs(bridge-ledger.equity.iloc[-1])>1


def test_outage_keeps_pairs_and_preserves_all_simultaneous_failure_flags(setup):
    tape,p,c,legs,day=setup
    s=compile_joint_stress(tape,c,legs,CASES[-1])
    s.price_reference[day+1,tape.pairs[day,0,0]]=-1e6
    s.price_reference[day+1,tape.pairs[day,0,1]]=1e6
    r=run_research(tape,'bm_spread',replace(p,end='2021-01-05'),stress=s)
    codes=set(r['events'].code)
    assert 'failed_nonpositive_equity' in codes and 'failed_proxy_collateral_shortfall' in codes
    h=r['holdings'].query("session == '2021-01-05' and product == 'WTI'")
    assert len(h)==2 and h.quantity.sum()==0


def test_invalid_anchor_clock_or_leg_coverage_rejected_at_boundary(setup):
    tape,p,c,legs,day=setup
    with pytest.raises(ValueError,match='observation clock'):
        compile_joint_stress(tape,c,legs.assign(observation='2021-01-04'),CASES[-1])
    with pytest.raises(ValueError,match='coverage'):
        compile_joint_stress(tape,c,legs.iloc[:1],CASES[-1])


def test_extended_outage_retains_a_paired_exit_failure_at_original_boundary(setup):
    tape,p,c,legs,day=setup
    changed=deepcopy(tape)
    changed.deadlines[changed.pairs[day,0]]=day+11
    s=compile_joint_stress(changed,c,legs,CASES[2])
    r=run_research(changed,'bm_spread',p,stress=s)
    assert r['status']=='failed_known_boundary_exit'
    assert r['ledger'].session.iloc[-1]==str(changed.dates[day+11].date())
    held=r['holdings'][r['holdings'].session.eq(r['ledger'].session.iloc[-1])]
    held=held[held['product'].eq('WTI')]
    assert len(held)==2 and held.quantity.sum()==0


def test_frozen_baseline_impulse_is_not_debited_without_actual_exposure(setup):
    tape,p,c,legs,day=setup
    changed=deepcopy(tape)
    for score in changed.updates.values():score['bm_spread_near_direction']=0
    s=compile_joint_stress(changed,c,legs,CASES[-1])
    r=run_research(changed,'bm_spread',p,stress=s)
    assert s.price_events.hypothetical_full_baseline_leg_impulse.sum()<0
    assert r['trades'].empty and r['ledger'].variation_margin.eq(0).all()
    assert r['ledger'].equity.eq(p.capital).all()
