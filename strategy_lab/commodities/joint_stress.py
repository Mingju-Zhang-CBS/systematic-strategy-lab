"""Conditional fixed-policy price, supply and proxy-collateral stress."""
from dataclasses import replace

import numpy as np
import pandas as pd

from .stress import compile_stress


CASES=(
 dict(name='control',capacity_fraction=1.,margin_multiple=1.,legs='both',duration=0,price_fraction=0.),
 dict(name='outage10',capacity_fraction=0.,margin_multiple=1.,legs='both',duration=10,price_fraction=0.),
 dict(name='outage20',capacity_fraction=0.,margin_multiple=1.,legs='both',duration=20,price_fraction=0.),
 dict(name='margin4_20',capacity_fraction=1.,margin_multiple=4.,legs='both',duration=20,price_fraction=0.),
 dict(name='price5_margin4_20',capacity_fraction=1.,margin_multiple=4.,legs='both',duration=20,price_fraction=.05),
 dict(name='outage20_margin4',capacity_fraction=0.,margin_multiple=4.,legs='both',duration=20,price_fraction=0.),
 dict(name='joint_outage10_price5_margin4',capacity_fraction=0.,margin_multiple=4.,legs='both',duration=10,price_fraction=.05),
 dict(name='joint_outage20_price5_margin4',capacity_fraction=0.,margin_multiple=4.,legs='both',duration=20,price_fraction=.05),
 dict(name='joint_outage20_price10_margin4',capacity_fraction=0.,margin_multiple=4.,legs='both',duration=20,price_fraction=.10),
)


def anchor_legs(tape,cohorts,trades,paired=False):
    """Construct invented-fixture anchors from original ordered control fills.

    Licensed work instead supplies independently frozen private anchors. Each
    side is the baseline post-addition position, not the stressed account's sign.
    """
    indices={k:i for i,k in enumerate(tape.contracts.contract)}
    selected={(r.entry_session,r.product):r.contracts.split(';') for r in cohorts.itertuples(index=False)}
    inventory={};captured=set();rows=[]
    for (session,product),g in trades.groupby(['session','product'],sort=False):
        fills=list(g.itertuples(index=False));step=2 if paired else 1
        for i in range(0,len(fills),step):
            batch=fills[i:i+step];adding=False
            for r in batch:
                old=inventory.get(r.contract,0);new=old+int(r.delta)
                adding|=abs(new)>abs(old) or old*new<0
                inventory[r.contract]=new
            event=(session,product)
            if adding and event in selected and event not in captured:
                captured.add(event);obs=tape.dates.get_loc(session)-2
                for r in batch:
                    valid=np.flatnonzero(np.isfinite(tape.prices[:obs+1,indices[r.contract]]))
                    index=int(valid[-1])
                    rows.append(dict(entry_session=session,product=product,contract=r.contract,
                        baseline_quantity=inventory[r.contract],observation=str(tape.dates[obs].date()),
                        anchor_session=str(tape.dates[index].date()),anchor_usd_per_unit=abs(tape.prices[index,indices[r.contract]])))
    return pd.DataFrame(rows,columns=['entry_session','product','contract','baseline_quantity','observation','anchor_session','anchor_usd_per_unit'])


def compile_joint_stress(tape,cohorts,legs,case):
    """Validate frozen leg/anchor inputs once, then build additive level steps.

    The underlying tape, signal directions and unit-risk histories are never
    mutated. Missing prices stay missing. Steps do not unwind at outage expiry.
    """
    supply=compile_stress(tape,cohorts,case)
    fields={'entry_session','product','contract','baseline_quantity','observation','anchor_session','anchor_usd_per_unit'}
    if (not fields<=set(legs) or legs[list(fields)].isna().any().any()
            or legs.duplicated(['entry_session','product','contract']).any()
            or not np.isfinite(case['price_fraction']) or not 0<=case['price_fraction']<=1
            or not np.isfinite(legs[['baseline_quantity','anchor_usd_per_unit']].to_numpy()).all()
            or legs.baseline_quantity.eq(0).any() or legs.anchor_usd_per_unit.lt(0).any()):
        raise ValueError('invalid joint stress leg specification')
    expected={(r.entry_session,r.product,k) for r in cohorts.itertuples(index=False) for k in r.contracts.split(';')}
    actual=set(zip(legs.entry_session,legs['product'],legs.contract))
    if expected!=actual:
        raise ValueError('joint stress leg coverage differs from frozen cohorts')
    indices={k:i for i,k in enumerate(tape.contracts.contract)}
    impulses=np.zeros_like(tape.prices)
    events=[]
    for r in legs.itertuples(index=False):
        day=tape.dates.get_loc(r.entry_session);obs=day-2;key=indices[r.contract]
        valid=np.flatnonzero(np.isfinite(tape.prices[:obs+1,key]))
        if (not len(valid) or r.observation!=str(tape.dates[obs].date())
                or r.anchor_session!=str(tape.dates[int(valid[-1])].date())
                or not np.isclose(r.anchor_usd_per_unit,abs(tape.prices[int(valid[-1]),key]),rtol=1e-12,atol=1e-12)):
            raise ValueError('joint stress anchor violates the frozen observation clock or USD units')
        shift=-np.sign(r.baseline_quantity)*case['price_fraction']*r.anchor_usd_per_unit
        start=day+1
        if start<len(tape.dates):
            impulses[start,key]+=shift
        events.append(dict(entry_session=r.entry_session,first_session='' if start>=len(tape.dates) else str(tape.dates[start].date()),
            product=r.product,contract=r.contract,baseline_quantity=r.baseline_quantity,
            observation=r.observation,anchor_session=r.anchor_session,anchor_usd_per_unit=r.anchor_usd_per_unit,
            price_fraction=case['price_fraction'],usd_per_unit_step=shift,
            hypothetical_full_baseline_leg_impulse=r.baseline_quantity*tape.contracts.multiplier.iloc[key]*shift))
    references=tape.prices+np.cumsum(impulses,axis=0)
    return replace(supply,price_reference=references,price_events=pd.DataFrame(events))
