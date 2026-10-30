"""A portfolio buffer cannot be spent twice or funded by a hoped-for exit."""
from copy import deepcopy
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.admission_resilience import cash_envelope,transition_surcharge
from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol,run_research
from strategy_lab.commodities.research_fixture import research_frames
from strategy_lab.commodities.joint_stress import CASES,anchor_legs,compile_joint_stress


@pytest.fixture(scope='module')
def setup():
    t=prepare(*research_frames());day=t.dates.get_loc('2021-01-04')
    p=ResearchProtocol(start='2021-01-04',end='2021-02-05',execution_policy='staged',exit_lead=10,entry_budget=True,joint_buffer=True)
    return t,p,day


def test_cash_algebra_charges_both_spread_sides_once():
    r=cash_envelope(np.array([2,-2]),np.array([50,50]),np.array([100,100]),np.array([5,5]),20_000,.1)
    assert r['gross']==20_000 and r['adverse_loss']==2_000
    assert np.isclose(r['stressed_reserve'],8_800) and r['round_trip_fees']==40
    assert r['cash_buffer']==2_000 and np.isclose(r['cash_slack'],7_160)


def test_cash_not_reused_by_two_individually_affordable_products():
    one=cash_envelope(np.array([1]),np.array([100]),np.array([100]),np.array([0]),10_000,.1)
    both=cash_envelope(np.array([1,1]),np.array([100,100]),np.array([100,100]),np.array([0,0]),10_000,.1)
    assert one['cash_admitted'] and not both['cash_admitted']


def test_negative_and_zero_prices_use_nonnegative_absolute_basis():
    a=cash_envelope(np.array([-2,1]),np.abs(np.array([-50,0])),np.ones(2),np.zeros(2),100,.1)
    assert a['gross']==100 and a['adverse_loss']==10


def test_announced_reserve_above_fixed_scenario_is_not_ignored():
    r=cash_envelope(np.array([1]),np.array([100]),np.array([100]),np.array([0]),10_000,.8)
    assert np.isclose(r['stressed_reserve'],8_800)


def test_long_outage_blocks_entry_that_original_drain_budget_allows(setup):
    t,p,day=setup;t=deepcopy(t);keys=t.pairs[day,0];t.deadlines[keys]=day+20
    old=run_research(t,'long_only',replace(p,joint_buffer=False,end=p.start))
    new=run_research(t,'long_only',replace(p,end=p.start))
    assert not old['trades'].query("product=='WTI'").empty
    assert new['trades'].query("product=='WTI'").empty
    a=new['resilience_entries'].query("product=='WTI'").iloc[0]
    assert not a.admitted and a.exit_budget_slack<0


def test_weaker_leg_and_entire_integer_target_enter_outage_budget(setup):
    t,p,day=setup;t=deepcopy(t)
    for score in t.updates.values():score['bm_spread_near_direction']=1
    k=t.pairs[day,0,1];t.volume[day-6,k]=100
    r=run_research(t,'bm_spread',replace(p,end=p.start))
    a=r['resilience_entries'].query("product=='WTI'").iloc[0]
    assert a.conservative_capacity==1
    assert a.required_drain_sessions==a.target_units
    assert a.exit_budget_slack==a.remaining_exit_sessions-20-a.target_units-2


def test_own_prior_cash_cannot_be_replaced_by_larger_lagged_equity(setup):
    t,p,_=setup
    r=run_research(t,'carry',replace(p,end='2021-01-05'))
    b=r['resilience_budgets'].iloc[-1]
    assert b.prior_cash<b.known_equity
    assert b.available_cash==b.prior_cash
    assert b.prior_cash==r['ledger'].equity.iloc[0]


def test_cash_envelope_uses_old_and_replacement_exposure_without_exit_credit(setup):
    t,p,day=setup;t=deepcopy(t)
    old=t.pairs[day,0].copy();third=t.contracts.index[t.contracts.contract.eq('SYN_RESEARCH_WTI_2')][0]
    t.pairs[day+1,0]=[old[1],third]
    r=run_research(t,'long_only',replace(p,end='2021-01-05'))
    budget=r['resilience_budgets'].iloc[-1]
    assert t.contracts.contract.iloc[old[0]] in budget.envelope_contracts
    assert budget.required_cash>=budget.existing_only_required-1e-8
    assert not budget.cash_admitted and budget.existing_only_deficit==0
    # The old close succeeds while the optional replacement is refused.
    fills=r['trades'].query("product=='WTI'")
    assert len(fills)==2 and fills.delta.sum()==0
    assert r['holdings'].query("session=='2021-01-05' and product=='WTI'").empty


def test_current_price_surprise_does_not_change_cash_admission(setup):
    t,p,day=setup;t=deepcopy(t)
    changed=deepcopy(t);changed.prices[day]*=20
    a=run_research(t,'long_only',replace(p,end=p.start));b=run_research(changed,'long_only',replace(p,end=p.start))
    for name in ['decisions','resilience_entries','resilience_budgets']:pd.testing.assert_frame_equal(a[name],b[name])


def test_future_observation_changes_no_earlier_buffer_or_fill(setup):
    t,p,day=setup;changed=deepcopy(t);changed.prices[day+3:]*=10;changed.volume[day+3:]=0
    short=replace(p,end='2021-01-06')
    a=run_research(t,'carry',short);b=run_research(changed,'carry',short)
    for name in ['ledger','trades','resilience_entries','resilience_budgets']:pd.testing.assert_frame_equal(a[name],b[name])


def test_earlier_retirement_closes_equal_units_and_never_reopens(setup):
    t,p,day=setup;t=deepcopy(t)
    for score in t.updates.values():score['bm_spread_near_direction']=1
    t.deadlines[t.pairs[day,0]]=day+26
    r=run_research(t,'bm_spread',replace(p,end='2021-01-20'))
    h=r['holdings'].query("product=='WTI'")
    assert not h.empty
    assert (h.groupby('session').quantity.sum()==0).all()
    plans=r['exit_plans'].query("product=='WTI' and early_retirement")
    assert not plans.empty
    last=plans.session.iloc[0]
    fills=r['trades'].query("product=='WTI' and session>=@last")
    assert fills.delta.abs().sum()>0
    first=r['trades'].query("product=='WTI' and session<@last").groupby('contract').delta.sum().to_dict()
    for (session,contract),g in fills.groupby(['session','contract'],sort=False):
        old=first.get(contract,0);new=old+int(g.delta.sum())
        assert abs(new)<=abs(old) and old*new>=0
        first[contract]=new


def test_protocol_flag_requires_entry_budget(setup):
    t,p,_=setup
    with pytest.raises(ValueError,match='invalid research protocol'):
        run_research(t,'carry',replace(p,entry_budget=False))


def test_a_larger_unbudgeted_price_gap_retains_cash_and_equity_failures(setup):
    t,p,day=setup;t=deepcopy(t)
    for score in t.updates.values():score['bm_spread_near_direction']=1
    old=run_research(t,'bm_spread',replace(p,joint_buffer=False))
    c=pd.DataFrame([dict(entry_session=p.start,product='WTI',contracts=';'.join(t.contracts.contract.iloc[t.pairs[day,0]]))])
    legs=anchor_legs(t,c,old['trades'],True)
    stress=compile_joint_stress(t,c,legs,CASES[-1])
    for leg in legs.itertuples(index=False):
        k=t.contracts.index[t.contracts.contract.eq(leg.contract)][0]
        stress.price_reference[day+1,k]=-np.sign(leg.baseline_quantity)*1e6
    r=run_research(t,'bm_spread',replace(p,end='2021-01-05'),stress=stress)
    assert r['status'].startswith('failed')
    assert {'failed_nonpositive_equity','failed_proxy_collateral_shortfall'}<=set(r['events'].code)
    h=r['holdings'].query("session=='2021-01-05' and product=='WTI'")
    assert len(h)==2 and h.quantity.sum()==0


def test_outage_longer_than_budget_keeps_original_paired_boundary_failure(setup):
    t,p,day=setup;t=deepcopy(t)
    for score in t.updates.values():score['bm_spread_near_direction']=1
    keys=t.pairs[day,0];t.deadlines[keys]=day+27
    old=run_research(t,'bm_spread',replace(p,joint_buffer=False))
    c=pd.DataFrame([dict(entry_session=p.start,product='WTI',contracts=';'.join(t.contracts.contract.iloc[keys]))])
    legs=anchor_legs(t,c,old['trades'],True)
    case=dict(CASES[2],duration=40)
    stress=compile_joint_stress(t,c,legs,case)
    r=run_research(t,'bm_spread',replace(p,end=str(t.dates[day+30].date())),stress=stress)
    assert r['status']=='failed_known_boundary_exit'
    assert r['ledger'].session.iloc[-1]==str(t.dates[day+27].date())
    h=r['holdings'][r['holdings'].session.eq(r['ledger'].session.iloc[-1])]
    pair=h[h['product'].eq('WTI')]
    assert len(pair)==2 and pair.quantity.sum()==0


def test_no_qualified_entries_is_reported_without_invented_positions(setup):
    t,p,day=setup;t=deepcopy(t)
    t.deadlines[t.pairs[day].ravel()]=day+3
    r=run_research(t,'long_only',replace(p,end=p.start))
    assert r['status']=='completed_no_qualified_trades'
    assert r['trades'].empty and r['holdings'].empty
    assert (r['ledger'].equity==p.capital).all()


def test_reversal_allowance_covers_three_fee_sides_on_equal_inventory():
    r=cash_envelope(np.array([2,-2]),np.array([50,50]),np.array([100,100]),np.array([5,5]),20_000,.1,20.)
    assert r['transition_fee_surcharge']==20 and r['round_trip_fees']==60
    assert np.isclose(r['required_cash'],12_860)


def test_same_contract_spread_flip_reserves_the_old_closing_sides(setup):
    t,p,day=setup;t=deepcopy(t)
    for score in t.updates.values():score['bm_spread_near_direction']=1
    update=t.updates[max(i for i in t.updates if i<=day)].copy()
    update.loc[update['product'].eq('WTI'),'bm_spread_near_direction']=-1
    t.updates[day+1]=update
    r=run_research(t,'bm_spread',replace(p,end='2021-01-05'))
    first=r['trades'].query("session=='2021-01-04' and product=='WTI'").set_index('contract')
    assert len(first)==2
    proposal=r['decisions'].query("session=='2021-01-05' and product=='WTI'").iloc[0]
    expected=0.
    for key in first.index:
        metadata=t.contracts[t.contracts.contract.eq(key)].iloc[0]
        expected+=min(abs(first.loc[key,'delta']),abs(proposal.requested_units))*(p.commission+p.slippage_ticks*metadata.outright_tick*metadata.multiplier)
    b=r['resilience_budgets'].iloc[-1]
    assert expected>0 and np.isclose(b.transition_fee_surcharge,expected)


def test_same_direction_deep_reduction_and_readd_covers_the_complete_route():
    old=np.array([12,-12]);reduced=np.array([1,-1]);target=np.array([11,-11])
    fee=transition_surcharge(old,reduced,target,np.ones(2))
    assert fee==16
    envelope=np.maximum(abs(old),abs(target))
    r=cash_envelope(envelope,np.ones(2),np.ones(2),np.ones(2),1_000,.1,fee)
    # Each leg pays eleven closing, ten reopening and eleven future-exit sides.
    assert r['round_trip_fees']==64
