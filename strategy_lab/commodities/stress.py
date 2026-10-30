"""Invented execution-capacity and proxy-collateral schedules, never SPAN data."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


CASES = (
    dict(name="control", capacity_fraction=1., margin_multiple=1., legs="both", duration=0),
    dict(name="capacity_half_5", capacity_fraction=.5, margin_multiple=1., legs="both", duration=5),
    dict(name="capacity_quarter_5", capacity_fraction=.25, margin_multiple=1., legs="both", duration=5),
    dict(name="one_leg_quarter_5", capacity_fraction=.25, margin_multiple=1., legs="last", duration=5),
    dict(name="capacity_zero_5", capacity_fraction=0., margin_multiple=1., legs="both", duration=5),
    dict(name="margin_double_5", capacity_fraction=1., margin_multiple=2., legs="both", duration=5),
    dict(name="combined_quarter_margin4_5", capacity_fraction=.25, margin_multiple=4., legs="both", duration=5),
)


@dataclass(frozen=True)
class StressSchedule:
    capacity_factor: np.ndarray
    margin_factor: np.ndarray
    windows: pd.DataFrame
    case: dict


def compile_stress(tape, cohorts, case):
    """Validate schedule input once; effective shocks start AFTER entry day.

    Contract order in a paired cohort is the frozen fill order. ``last`` stresses
    its last leg only; an outright has one leg. Overlaps use min capacity / max
    margin rather than multiplying shocks. Events never move to chase exposure.
    """
    required={"entry_session", "product", "contracts"}
    if (not required <= set(cohorts) or cohorts[list(required)].isna().any().any()
            or cohorts.duplicated(["entry_session", "product"]).any()
            or not np.isfinite([case["capacity_fraction"],case["margin_multiple"],case["duration"]]).all()
            or not 0 <= case["capacity_fraction"] <= 1 or case["margin_multiple"] < 1
            or case["duration"] < 0 or case["duration"] != int(case["duration"])
            or case["legs"] not in {"both","last"}):
        raise ValueError("invalid stress schedule or assumptions")
    dates=tape.dates
    indices={s:i for i,s in enumerate(tape.contracts.contract)}
    products=tape.contracts.set_index("contract")["product"].to_dict()
    factors=np.ones(tape.prices.shape,dtype=np.float32)
    margins=np.ones(len(dates))
    windows=[]
    for r in cohorts.itertuples(index=False):
        day=pd.Timestamp(r.entry_session)
        keys=r.contracts.split(";")
        if (day not in dates or len(keys) not in {1,2} or len(set(keys))!=len(keys)
                or any(k not in indices or products[k]!=r.product for k in keys)):
            raise ValueError("stress cohort date or contract identity mismatch")
        entry=dates.get_loc(day)
        start=entry+1
        end=min(start+int(case["duration"]),len(dates))
        affected=keys[-1:] if case["legs"]=="last" else keys
        columns=[indices[k] for k in affected]
        factors[start:end,columns]=np.minimum(factors[start:end,columns],case["capacity_fraction"])
        margins[start:end]=np.maximum(margins[start:end],case["margin_multiple"])
        windows.append(dict(entry_session=str(day.date()),product=r.product,contracts=r.contracts,
                            affected_contracts=";".join(affected),
                            first_session="" if start>=len(dates) else str(dates[start].date()),
                            last_session="" if end<=start else str(dates[end-1].date()),
                            scheduled_sessions=end-start,capacity_fraction=case["capacity_fraction"],
                            margin_multiple=case["margin_multiple"]))
    return StressSchedule(factors,margins,pd.DataFrame(windows),dict(case))


def entry_cohorts(trades, paired=False):
    """First actual added risk per product/year, from ordered baseline fills.

    Used for independently generated synthetic examples. Licensed real cohorts
    are frozen privately before stress results and supplied through CSV.
    """
    inventory={}
    chosen=set()
    rows=[]
    for (session,product),group in trades.groupby(["session","product"],sort=False):
        fills=list(group.itertuples(index=False))
        step=2 if paired else 1
        for start in range(0,len(fills),step):
            batch=fills[start:start+step]
            addition=False
            for r in batch:
                old=inventory.get(r.contract,0)
                new=old+int(r.delta)
                addition|=abs(new)>abs(old) or old*new<0
                inventory[r.contract]=new
            key=(session[:4],product)
            if addition and key not in chosen:
                chosen.add(key)
                rows.append(dict(entry_session=session,product=product,contracts=";".join(r.contract for r in batch),
                                 target_units=max(abs(inventory[r.contract]) for r in batch)))
    return pd.DataFrame(rows,columns=["entry_session","product","contracts","target_units"])
