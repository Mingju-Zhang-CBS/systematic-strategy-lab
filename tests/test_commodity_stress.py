"""Capacity surprises are execution outcomes; collateral is an encumbrance."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol,run_research
from strategy_lab.commodities.research_fixture import research_frames
from strategy_lab.commodities.stress import CASES,compile_stress,entry_cohorts


@pytest.fixture(scope="module")
def setup():
    tape=prepare(*research_frames())
    day=tape.dates.get_loc('2021-01-04')
    keys=tape.contracts.contract.iloc[tape.pairs[day,0]].tolist()
    cohorts=pd.DataFrame([dict(entry_session='2021-01-04',product='WTI',contracts=';'.join(keys))])
    p=ResearchProtocol(start='2021-01-04',end='2021-01-13',execution_policy='staged',exit_lead=10,entry_budget=True)
    return tape,p,cohorts,day


def test_schedule_excludes_entry_day_and_overlaps_do_not_compound(setup):
    tape,_,cohorts,day=setup
    c=pd.concat([cohorts,cohorts.assign(entry_session='2021-01-05')],ignore_index=True)
    s=compile_stress(tape,c,CASES[-1])
    keys=tape.pairs[day,0]
    assert (s.capacity_factor[day,keys]==1).all() and s.margin_factor[day]==1
    assert (s.capacity_factor[day+1:day+6,keys]==.25).all()
    assert s.margin_factor[day+2]==4 and s.margin_factor[day+7]==1


def test_one_leg_constraint_and_actual_reductions_remain_paired(setup):
    tape,p,c,day=setup
    tape=deepcopy(tape)
    for score in tape.updates.values():
        score['bm_spread_near_direction']=1
    # Freeze a replacement request immediately after entry, then constrain just
    # the old far member. The paired execution supply, not a future target, shrinks.
    tape.pairs[day+1,0]=tape.pairs[day+1,0][::-1]
    s=compile_stress(tape,c,{**CASES[3],'capacity_fraction':.002})
    r=run_research(tape,'bm_spread',p,stress=s)
    first=r['trades'].query("session == '2021-01-04' and product == 'WTI'")
    assert len(first)==2 and first.delta.sum()==0
    assert first.delta.abs().min()>1
    next_fills=r['trades'].query("session == '2021-01-05' and product == 'WTI'")
    assert len(next_fills)==2 and next_fills.delta.abs().eq(1).all()
    plan=r['exit_plans'].query("session == '2021-01-05' and product == 'WTI'").iloc[0]
    assert plan.planned_units>1
    for _,g in r['trades'].query("product == 'WTI'").groupby('session',sort=False):
        for i in range(0,len(g),2):
            assert g.iloc[i:i+2].delta.sum()==0
    held=r['holdings'].query("product == 'WTI'")
    assert held.groupby('session').quantity.sum().eq(0).all()
    np.testing.assert_allclose(s.capacity_factor[day+1,tape.pairs[day,0]],[1,.002])


def test_zero_offer_keeps_inventory_instead_of_inventing_a_fill(setup):
    tape,p,c,day=setup
    tape=deepcopy(tape)
    tape.deadlines[tape.pairs[day,0,0]]=day+11
    s=compile_stress(tape,c,CASES[4])
    r=run_research(tape,'long_only',p,stress=s)
    t=r['trades'].query("product == 'WTI'")
    assert len(t[t.session=='2021-01-04'])==1
    assert t[t.session.between('2021-01-05','2021-01-11')].empty
    assert r['events'].detail.eq('stressed_shared_capacity_limit').any()
    b=r['stress_budgets'].query("product == 'WTI' and session == '2021-01-05'").iloc[0]
    assert b.current_shock and b.offered_capacity==0 and b.conservative_capacity>0


def test_current_capacity_surprise_cannot_change_frozen_admission(setup):
    tape,p,c,_=setup
    p=replace(p,end='2021-01-05')
    a=run_research(tape,'long_only',p,stress=compile_stress(tape,c,CASES[1]))
    b=run_research(tape,'long_only',p,stress=compile_stress(tape,c,CASES[4]))
    pd.testing.assert_frame_equal(a['entry_admissions'],b['entry_admissions'])
    pd.testing.assert_frame_equal(a['decisions'],b['decisions'])


def test_future_shocks_do_not_change_historical_ledger(setup):
    tape,p,c,day=setup
    s=compile_stress(tape,c,CASES[-1])
    other=deepcopy(s)
    other.capacity_factor[day+2:]=0
    other.margin_factor[day+2:]=1000
    p=replace(p,end='2021-01-05')
    a=run_research(tape,'long_only',p,stress=s)
    b=run_research(tape,'long_only',p,stress=other)
    for name in ('ledger','trades','entry_admissions','stress_sessions'):
        pd.testing.assert_frame_equal(a[name],b[name])


def test_margin_announcement_is_current_not_anticipated_at_entry(setup):
    tape,p,c,day=setup
    s=compile_stress(tape,c,CASES[5])
    a=run_research(tape,'long_only',replace(p,end='2021-01-04'))
    b=run_research(tape,'long_only',replace(p,end='2021-01-04'),stress=s)
    pd.testing.assert_frame_equal(a['ledger'],b['ledger'])
    assert s.margin_factor[day]==1 and s.margin_factor[day+1]==2


def test_proxy_cash_shortfall_is_failure_without_double_debit(setup):
    tape,p,c,day=setup
    s=compile_stress(tape,c,{**CASES[-1],'capacity_fraction':0,'margin_multiple':1000})
    # Shock margin is portfolio-wide; prevent closing other inventory as well.
    s.capacity_factor[day+1:day+6]=0
    r=run_research(tape,'long_only',p,stress=s)
    assert r['status']=='failed_proxy_collateral_shortfall'
    assert r['stress_sessions'].collateral_shortfall.iloc[-1]>0
    l=r['ledger']
    np.testing.assert_allclose(l.equity,l.opening_equity+l.variation_margin-l.costs,atol=1e-8)
    assert l.free_cash.iloc[-1]<0 and abs(r['reconciliation']['terminal_error'])<1e-6


def test_synthetic_cohorts_keep_fixed_first_product_year_addition(setup):
    tape,p,_,_=setup
    r=run_research(tape,'long_only',p)
    c=entry_cohorts(r['trades'])
    assert not c.assign(year=c.entry_session.str[:4]).duplicated(['year','product']).any()
    assert c.entry_session.eq('2021-01-04').all()


def test_risk_buffer_breach_is_not_automatically_cash_insolvency(setup):
    tape,p,c,day=setup
    first=run_research(tape,'long_only',replace(p,end='2021-01-04'))
    l=first['ledger'].iloc[0]
    multiple=.75*l.equity/(p.reserve_rate*l.gross_proxy)
    s=compile_stress(tape,c,{**CASES[-1],'capacity_fraction':0,'margin_multiple':multiple})
    s.capacity_factor[day+1:]=0
    r=run_research(tape,'long_only',replace(p,end='2021-01-05'),stress=s)
    assert not r['status'].startswith('failed')
    row=r['stress_sessions'].iloc[-1]
    assert row.risk_buffer_breach and row.collateral_shortfall==0
    assert r['ledger'].free_cash.iloc[-1]>0


def test_all_actual_sides_share_the_current_offered_limit(setup):
    tape,p,c,day=setup
    s=compile_stress(tape,c,CASES[2])
    r=run_research(tape,'long_only',p,stress=s)
    by_id={k:i for i,k in enumerate(tape.contracts.contract)}
    for (session,key),g in r['trades'].groupby(['session','contract']):
        d=tape.dates.get_loc(session)
        k=by_id[key]
        raw=np.floor(.01*tape.volume[d-2,k])
        cap=min(np.floor(raw*s.capacity_factor[d-2,k]),np.floor(raw*s.capacity_factor[d,k]))
        assert g.delta.abs().sum()<=cap


def test_invalid_raw_schedule_fails_at_compiler_boundary(setup):
    tape,_,c,_=setup
    with pytest.raises(ValueError,match='invalid stress'):
        compile_stress(tape,c,{**CASES[1],'capacity_fraction':-1})
    with pytest.raises(ValueError,match='identity mismatch'):
        compile_stress(tape,c.assign(contracts='UNKNOWN'),CASES[1])
