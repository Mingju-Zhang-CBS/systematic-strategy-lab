"""Multi-asset total-return-unit accounts with exact after-fee target funding."""
import numpy as np
import pandas as pd
from scipy.optimize import brentq


def funded_rebalance(units,cash,prices,weights,cost_bps):
    units=np.asarray(units,float);p=np.asarray(prices,float);w=np.asarray(weights,float)
    if units.ndim!=1 or units.shape!=p.shape or p.shape!=w.shape:
        raise ValueError("Aligned one-dimensional account arrays required")
    if (not np.isfinite(np.r_[units,p,w,cash,cost_bps]).all() or (units<0).any()
            or cash < -1e-8 or (p<=0).any() or (w<0).any() or w.sum()>1+1e-10
            or not 0<=cost_bps<10000):
        raise ValueError("Invalid long-only funded account")
    old=units*p;pre=float(old.sum()+cash);c=cost_bps/10000
    if pre<=0:raise ValueError("Positive equity required")
    value=pre if c==0 else brentq(lambda v:v+c*np.abs(w*v-old).sum()-pre,0.,pre,xtol=1e-10,rtol=1e-14)
    delta=w*value-old;fee=c*np.abs(delta)
    new_cash=float(cash-delta.sum()-fee.sum())
    if new_cash < -1e-7:raise ArithmeticError("Rebalance overdrew cash")
    return w*value/p,max(0.,new_cash),delta,fee


def backtest(prices,targets,initial_nav=100000.,cost_bps=5.,cash_rate=0.):
    if (not len(targets) or not prices.index.is_monotonic_increasing or prices.index.has_duplicates
            or not targets.index.is_monotonic_increasing or targets.index.has_duplicates
            or not prices.columns.equals(targets.columns) or not targets.index.isin(prices.index).all()
            or prices.index[0]!=targets.index[0]):
        raise ValueError("Aligned prices and scheduled target dates required")
    if (not np.isfinite(prices.to_numpy()).all() or (prices.to_numpy()<=0).any()
            or not np.isfinite(targets.to_numpy()).all() or (targets.to_numpy()<0).any()
            or (targets.sum(axis=1)>1+1e-10).any() or not np.isfinite([cash_rate,initial_nav,cost_bps]).all()
            or cash_rate<0 or initial_nav<=0 or not 0<=cost_bps<10000):
        raise ValueError("Invalid prices, target fractions or funding assumptions")
    assets=list(prices.columns);unit=np.zeros(len(assets));cash=float(initial_nav);previous=float(initial_nav)
    previous_price=prices.iloc[0].to_numpy();previous_date=prices.index[0]
    pending=None;ledger=[];trades=[];decisions=[]
    for i,(date,price) in enumerate(prices.iterrows()):
        p=price.to_numpy(float);days=(date-previous_date).days
        cash_return=float(np.expm1(cash_rate*days/365.25));interest=cash*cash_return
        held=unit*previous_price/previous;pnl=float(unit@(p-previous_price));cash+=interest
        pre=float(unit@p+cash);fees=0.;gross=0.;decision_date=""
        if pending is not None:
            observed,w=pending;unit,cash,delta,fee=funded_rebalance(unit,cash,p,w,cost_bps)
            fees=float(fee.sum());gross=float(np.abs(delta).sum());decision_date=str(observed.date())
            for j,a in enumerate(assets):
                if delta[j]!=0:
                    trades.append({"decision_date":decision_date,"execution_date":str(date.date()),
                                   "ticker":a,"model_unit_price":p[j],"quantity":delta[j]/p[j],
                                   "signed_notional":delta[j],"fee":fee[j],"target_weight":w[j]})
        nav=float(unit@p+cash);bridge=nav-previous-pnl-interest+fees;end=unit*p/nav
        if abs(bridge)>1e-7 or cash<0 or end.sum()>1+1e-10:
            raise ArithmeticError("Account bridge, cash or long-only exposure failed")
        row={"date":str(date.date()),"prior_nav":previous,"nav":nav,"return":nav/previous-1,
             "cash":cash,"cash_interest":interest,"cash_return":cash_return,"security_pnl":pnl,
             "fee":fees,"gross_traded":gross,"turnover":gross/pre,"held_exposure":float(held.sum()),
             "end_exposure":float(end.sum()),"bridge_error":bridge,"executed_decision_date":decision_date}
        for j,a in enumerate(assets):row.update({"units_"+a:unit[j],"price_"+a:p[j],"held_weight_"+a:held[j],"end_weight_"+a:end[j]})
        ledger.append(row);pending=None
        if date in targets.index:
            w=targets.loc[date].to_numpy();can_execute=i+1<len(prices)
            decisions.append({"decision_date":str(date.date()),"execution_date":str(prices.index[i+1].date()) if can_execute else "",
                              "status":"scheduled" if can_execute else "not_executed_end_of_snapshot",
                              **{"target_"+a:float(w[j]) for j,a in enumerate(assets)}})
            if can_execute:pending=(date,w.copy())
        previous=nav;previous_price=p;previous_date=date
    return (pd.DataFrame(ledger),pd.DataFrame(decisions),pd.DataFrame(trades,columns=["decision_date","execution_date","ticker","model_unit_price","quantity","signed_notional","fee","target_weight"]))


def metrics(ledger):
    r=ledger["return"].to_numpy();excess=r-ledger.cash_return.to_numpy();years=len(r)/252
    wealth=np.r_[1.,np.cumprod(1+r)];sd=excess.std(ddof=1) if len(r)>1 else 0.
    held=ledger[[c for c in ledger if c.startswith("held_weight_")]].to_numpy()
    exposure=held.sum(axis=1);relative=np.divide(held,exposure[:,None],out=np.zeros_like(held),where=exposure[:,None]>0)
    hhi=(relative**2).sum(axis=1);invested=hhi>0
    return {"observations":len(r),"total_return":float(wealth[-1]-1),"cagr":float(wealth[-1]**(1/years)-1),
            "annualized_volatility":float(r.std(ddof=1)*np.sqrt(252)),
            "excess_sharpe":float(excess.mean()/sd*np.sqrt(252)) if sd>1e-15 else None,
            "max_drawdown":float((wealth/np.maximum.accumulate(wealth)-1).min()),
            "annualized_turnover":float(ledger.turnover.sum()/years),"average_held_exposure":float(exposure.mean()),
            "average_risky_hhi":float(hhi[invested].mean()) if invested.any() else None,
            "average_effective_assets":float((1/hhi[invested]).mean()) if invested.any() else None,
            "total_fees":float(ledger.fee.sum()),"min_cash":float(ledger.cash.min()),
            "maximum_account_residual":float(ledger.bridge_error.abs().max())}
