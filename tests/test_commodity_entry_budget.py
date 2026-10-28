"""Admission and retirement use one budget, with no same-day exit credit."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.engine import PRODUCTS
from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol, _entry_budget, run_research
from strategy_lab.commodities.research_fixture import research_frames


@pytest.fixture(scope="module")
def panel():
    return prepare(*research_frames())


def admission_tape(panel, spread=False):
    tape=deepcopy(panel)
    day=tape.dates.get_loc("2021-01-04")
    j=PRODUCTS.index("WTI")
    old=tape.pairs[day,j].copy()
    third=tape.contracts.index[tape.contracts.contract.eq("SYN_RESEARCH_WTI_2")][0]
    if spread:
        for score in tape.updates.values():
            score["bm_spread_near_direction"]=1
    p=ResearchProtocol(start="2021-01-04",end="2021-01-05",execution_policy="staged",exit_lead=10,entry_budget=True)
    return tape,p,day,j,old,third


def test_strict_lead_and_drain_boundaries_exclude_entry_day():
    assert not _entry_budget(1,100,10,10,2)["admitted"]
    assert _entry_budget(1,100,11,10,2)["admitted"]
    assert not _entry_budget(22,2,13,10,2)["admitted"]
    assert _entry_budget(22,2,14,10,2)["admitted"]
    assert not _entry_budget(1,0,100,10,2)["admitted"]


def test_late_new_entry_is_refused_without_clipping_to_a_smaller_order(panel):
    tape,p,day,_,old,_=admission_tape(panel)
    tape.deadlines[old[0]]=day+3
    config=replace(p,end=p.start)
    baseline=run_research(tape,"long_only",replace(config,entry_budget=False))
    assert not baseline["trades"].query("product == 'WTI'").empty
    r=run_research(tape,"long_only",config)
    assert r["trades"].query("product == 'WTI'").empty
    a=r["entry_admissions"].query("product == 'WTI'").iloc[0]
    assert a.remaining_exit_sessions==3 and not a.admitted
    assert a.target_units>1 and "inside_retirement_lead" in a.reason


def test_weaker_spread_leg_controls_whole_basket_admission(panel):
    tape,p,day,_,old,_=admission_tape(panel,True)
    tape.volume[day-6:day-1,old[1]]=np.nan
    r=run_research(tape,"bm_spread",replace(p,end=p.start))
    assert r["trades"].query("product == 'WTI'").empty
    a=r["entry_admissions"].query("product == 'WTI'").iloc[0]
    assert a.paired and a.conservative_capacity==0 and not a.admitted


def test_earliest_spread_deadline_controls_admission(panel):
    tape,p,day,_,old,_=admission_tape(panel,True)
    tape.deadlines[old[0]]=day+100
    tape.deadlines[old[1]]=day+5
    r=run_research(tape,"bm_spread",replace(p,end=p.start))
    a=r["entry_admissions"].query("product == 'WTI'").iloc[0]
    assert a.remaining_exit_sessions==5 and not a.admitted
    assert r["holdings"].query("product == 'WTI'").empty


def test_increase_checks_total_post_trade_units_not_only_increment(panel):
    tape,p,day,_,old,_=admission_tape(panel)
    tape.deadlines[old[0]]=day+17
    tape.volume[day-5,old[0]]=100  # conservative 1, current entry allowance remains high
    score=tape.updates[max(i for i in tape.updates if i<=day)].copy()
    score["long_only_direction"]=(score["product"]=="WTI").astype(int)
    tape.updates[day+1]=score
    # Construct a deterministic counterexample between incremental and total
    # requirements; no assumption about the fixture's risk-sized quantity.
    proposal=run_research(tape,"long_only",replace(p,entry_budget=False))
    prior=int(proposal["holdings"].query("session == '2021-01-04' and product == 'WTI'").quantity.iloc[0])
    requested=int(proposal["decisions"].query("session == '2021-01-05' and product == 'WTI'").requested_units.iloc[0])
    remaining=max(11,requested-prior+3)
    assert remaining<requested+2
    tape.deadlines[old[0]]=day+1+remaining
    r=run_research(tape,"long_only",p)
    a=r["entry_admissions"].query("session == '2021-01-05' and product == 'WTI'").iloc[0]
    assert a.target_units>a.current_units>0 and not a.admitted
    assert _entry_budget(int(a.target_units-a.current_units),1,int(a.remaining_exit_sessions),10,2)["admitted"]
    assert r["trades"].query("session == '2021-01-05' and product == 'WTI'").empty


def test_rejected_replacement_does_not_block_or_undo_old_close(panel):
    tape,p,day,j,old,third=admission_tape(panel)
    tape.pairs[day+1,j]=[old[1],third]
    tape.volume[day-5,old[1]]=0
    r=run_research(tape,"long_only",p)
    assert r["holdings"].query("session == '2021-01-05' and product == 'WTI'").empty
    closes=r["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(closes)==1 and closes.delta.iloc[0]<0 and closes.cost.iloc[0]>0
    assert not r["entry_admissions"].query("session == '2021-01-05' and product == 'WTI'").admitted.any()


def test_rejected_new_spread_keeps_partial_old_exit_paired(panel):
    tape,p,day,j,old,third=admission_tape(panel,True)
    tape.pairs[day+1,j]=[old[1],third]
    tape.volume[day-1,old[1]]=100
    tape.volume[day-5,third]=0
    r=run_research(tape,"bm_spread",p)
    held=r["holdings"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(held)==2 and held.quantity.sum()==0
    fills=r["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(fills)==2 and fills.delta.sum()==0
    assert fills.delta.abs().eq(1).all()


def test_equal_size_direction_reversal_is_also_an_entry(panel):
    tape,p,day,_,old,_=admission_tape(panel)
    tape.deadlines[old[0]]=day+11  # first request has 11 exit sessions; reversal has 10
    score=tape.updates[max(i for i in tape.updates if i<=day)].copy()
    score.loc[score["product"]=="WTI","long_only_direction"]=-1
    tape.updates[day+1]=score
    r=run_research(tape,"long_only",p)
    assert not r["holdings"].query("session == '2021-01-04' and product == 'WTI'").empty
    assert r["holdings"].query("session == '2021-01-05' and product == 'WTI'").empty
    a=r["entry_admissions"].query("session == '2021-01-05' and product == 'WTI'").iloc[0]
    assert not a.admitted and a.remaining_exit_sessions==10


def test_execution_reference_and_future_activity_cannot_change_frozen_gate(panel):
    tape,p,day,_,_,_=admission_tape(panel)
    changed=deepcopy(tape)
    changed.prices[day+1:]*=4
    changed.volume[day+1:]=0
    a,b=run_research(tape,"long_only",p),run_research(changed,"long_only",p)
    pd.testing.assert_frame_equal(a["entry_admissions"],b["entry_admissions"])
    pd.testing.assert_frame_equal(a["decisions"],b["decisions"])


def test_future_data_cannot_change_historical_gate_or_funded_ledger(panel):
    tape,p,day,_,_,_=admission_tape(panel)
    p=replace(p,end="2021-02-05")
    changed=deepcopy(tape)
    future=changed.dates>pd.Timestamp(p.end)
    changed.prices[future]*=4
    changed.volume[future]=0
    a,b=run_research(tape,"carry",p),run_research(changed,"carry",p)
    for name in ("entry_admissions","exit_plans","ledger","trades"):
        pd.testing.assert_frame_equal(a[name],b[name])


def test_entry_gate_requires_a_valid_staged_retirement_protocol(panel):
    with pytest.raises(ValueError,match="invalid research"):
        run_research(panel,"carry",ResearchProtocol(entry_budget=True))
