"""Fixed-rule long-only allocation and a self-financing event ledger."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np
import pandas as pd

ASSETS=("SPY","IEF","GLD","DBC")
TICKERS=ASSETS+("QQQ",)

@dataclass(frozen=True)
class Config:
    lookback: int=252
    skip: int=21
    covariance_window: int=126
    vol_target: float=.10
    asset_cap: float=.50
    gross_cap: float=.99
    cost_bps: float=3.
    execution_delay: int=1
    dividend_payment_lag: int=20
    initial_nav: float=100_000.

    def validate(self):
        if self.lookback<2 or not 0<=self.skip<self.lookback or self.covariance_window<2:
            raise ValueError("Invalid history windows")
        if self.execution_delay<1 or self.dividend_payment_lag<0:
            raise ValueError("Execution delay >=1; payment lag >=0")
        if not all(np.isfinite(v) for v in asdict(self).values()):raise ValueError("Finite configuration required")
        if not (0<self.asset_cap<=1 and 0<self.gross_cap<=1 and self.vol_target>0 and self.initial_nav>0 and self.cost_bps>=0):
            raise ValueError("Invalid risk or cost limits")
        if any(not isinstance(v,int) for v in [self.lookback,self.skip,self.covariance_window,self.execution_delay,self.dividend_payment_lag]):
            raise ValueError("Windows and lags must be integer observations")


def synthetic_market(days=1512,seed=2026):
    """A stylized five-asset market. Tickers name roles, not historical returns."""
    rng=np.random.default_rng(seed);dates=pd.bdate_range("2019-01-02",periods=days)
    market=rng.normal(size=days);regime=np.sin(np.arange(days)/160)
    levels=np.array([100.,90.,80.,70.,120.]);prices=np.empty((days,5));div=np.zeros_like(prices);split=np.ones_like(prices)
    for i in range(days):
        drift=np.array([.00025,.00008,.00010,.00005,.00035])+regime[i]*np.array([.00045,-.0001,.0002,.0003,.0006])
        shock=np.array([.009,.003,.006,.007,.012])*(.5*market[i]+np.sqrt(.75)*rng.normal(size=5))
        economic=levels*np.exp(drift+shock)
        if i>0 and i%63==0:div[i]=economic*np.array([.003,.004,0.,0.,.001])
        if i==800:split[i,0]=2.
        levels=economic/split[i]-div[i]
        prices[i]=levels
    volumes=rng.integers(1_000_000,8_000_000,size=(days,5))
    return pd.DataFrame({"date":np.repeat(dates,5),"ticker":list(TICKERS)*days,
        "close":prices.ravel(),"dividend":div.ravel(),"split":split.ravel(),"volume":volumes.ravel(),
        "cash_rate":np.repeat(.02+.005*(1+np.sin(np.arange(days)/300)),5)})


def validate_market(frame):
    required={"date","ticker","close","dividend","split","volume","cash_rate"}
    if not required.issubset(frame):raise ValueError(f"Missing columns: {sorted(required-set(frame))}")
    d=frame[list(sorted(required))].copy();d["date"]=pd.to_datetime(d.date,errors="raise")
    if d.date.isna().any() or d.date.dt.tz is not None or not d.date.eq(d.date.dt.normalize()).all():
        raise ValueError("Dates must be nonmissing, timezone-naive, midnight session dates")
    if d.duplicated(["date","ticker"]).any():raise ValueError("Duplicate date/ticker")
    if set(d.ticker)!=set(TICKERS):raise ValueError("Exactly SPY,IEF,GLD,DBC,QQQ required")
    numeric=["close","dividend","split","volume","cash_rate"]
    d[numeric]=d[numeric].apply(pd.to_numeric,errors="raise")
    if not np.isfinite(d[numeric].to_numpy()).all():raise ValueError("No missing or nonfinite market fields")
    if (d.close<=0).any() or (d.split<=0).any() or (d.dividend<0).any() or (d.volume<0).any():
        raise ValueError("Prices/splits positive; dividends/volume nonnegative")
    groups=d.groupby("date")
    if not groups.size().eq(5).all() or not groups.cash_rate.nunique().eq(1).all():
        raise ValueError("Complete common sessions and one annual cash rate per session required")
    if (groups.cash_rate.first().abs()>1).any():raise ValueError("Cash rate is an annual decimal, bounded in absolute value by 1")
    return d.sort_values(["date","ticker"]).reset_index(drop=True)


def arrays(frame):
    d=validate_market(frame)
    table=lambda col:d.pivot(index="date",columns="ticker",values=col).reindex(columns=TICKERS)
    prices=table("close");div=table("dividend").to_numpy();splits=table("split").to_numpy()
    p=prices.to_numpy();ret=np.zeros_like(p);ret[1:]=splits[1:]*(p[1:]+div[1:])/p[:-1]-1
    tri=np.cumprod(1+ret,axis=0);rates=d.groupby("date").cash_rate.first().reindex(prices.index).to_numpy()
    return prices.index,p,div,splits,ret,tri,rates


def target_weights(index,returns,total_return_index,config,mode):
    weights=np.zeros(5)
    if mode in {"spy","qqq"}:
        weights[0 if mode=="spy" else 4]=config.gross_cap;return weights
    if mode=="static":weights[:4]=min(config.gross_cap/4,config.asset_cap);return weights
    if mode!="momentum":raise ValueError("Unknown strategy mode")
    momentum=total_return_index[index-config.skip,:4]/total_return_index[index-config.lookback,:4]-1
    eligible=momentum>0
    if eligible.any():weights[:4][eligible]=min(config.asset_cap,config.gross_cap/eligible.sum())
    cov=np.cov(returns[index-config.covariance_window+1:index+1,:4].T,ddof=1)*252
    risk=float(np.sqrt(max(0.,weights[:4]@cov@weights[:4])))
    if risk>config.vol_target:weights*=config.vol_target/risk
    return weights


def rebalance(shares,cash,nav,prices,weights,cost_bps):
    """Frozen weights; integer execution quantities using currently observed NAV.

    Sell first, then pro-rate unaffordable purchases including their fees.
    Receivables are part of NAV but cannot finance purchases before payment.
    """
    target=np.floor(weights*nav/prices)
    delta=target-shares;fee_rate=cost_bps/10_000
    sold=np.minimum(delta,0.)
    cash-=float(np.sum(sold*prices)+np.sum(np.abs(sold)*prices)*fee_rate)
    shares=shares+sold
    desired=np.maximum(target-shares,0.)
    required=float(np.sum(desired*prices)*(1+fee_rate))
    scale=min(1.,max(0.,cash)/required) if required else 1.
    bought=np.floor(desired*scale+1e-12)
    cash-=float(np.sum(bought*prices)*(1+fee_rate));shares+=bought
    trades=sold+bought
    fees=float(np.sum(np.abs(trades)*prices)*fee_rate)
    if cash < -1e-7:raise AssertionError("Purchase generated an overdraft")
    return shares,max(0.,cash),trades,fees


def backtest(frame,config=Config(),mode="momentum"):
    config.validate();dates,p,div,splits,ret,tri,rates=arrays(frame)
    start=max(config.lookback,config.covariance_window)
    if len(dates)<=start+config.execution_delay+2:raise ValueError("Insufficient warmup/evaluation observations")
    if mode not in {"momentum","static","spy","qqq"}:raise ValueError("Unknown mode")
    shares=np.zeros(5);cash=config.initial_nav;receivable=0.;prior_nav=config.initial_nav
    due={};pending={};ledger=[];decisions=[];orders=[]
    for i in range(start,len(dates)):
        before=shares.copy();dt=(dates[i]-dates[i-1]).days/365.25
        interest=cash*np.expm1(rates[i-1]*dt);cash+=interest
        shares*=splits[i]
        security_pnl=float(shares@p[i]-before@p[i-1])
        entitlement=float(shares@div[i]);receivable+=entitlement
        due[i+config.dividend_payment_lag]=due.get(i+config.dividend_payment_lag,0.)+entitlement
        payment=due.pop(i,0.);cash+=payment;receivable-=payment
        nav_before=cash+receivable+float(shares@p[i]);fees=0.;notional=0.
        if i in pending:
            decision,weights=pending.pop(i)
            shares,cash,trades,fees=rebalance(shares,cash,nav_before,p[i],weights,config.cost_bps)
            notional=float(np.sum(np.abs(trades)*p[i]))
            for j,qty in enumerate(trades):
                if qty:orders.append({"decision_date":dates[decision],"execution_date":dates[i],"ticker":TICKERS[j],
                                      "quantity":float(qty),"price":float(p[i,j]),"fee":float(abs(qty)*p[i,j]*config.cost_bps/10000)})
        nav=cash+receivable+float(shares@p[i])
        bridge=nav-prior_nav-security_pnl-entitlement-interest+fees
        if abs(bridge)>1e-7:raise AssertionError(f"NAV accounting mismatch: {bridge}")
        record={"date":dates[i],"nav":nav,"prior_nav":prior_nav,"return":nav/prior_nav-1,"cash":cash,
                "receivable":max(0.,receivable),"security_pnl":security_pnl,"dividend_accrual":entitlement,
                "dividend_payment":payment,"cash_interest":interest,"cost":fees,"traded_notional":notional,
                "turnover":notional/prior_nav,"bridge_error":bridge,
                "cash_return":float(np.expm1(rates[i-1]*dt)),"elapsed_days":(dates[i]-dates[i-1]).days}
        record.update({"shares_"+t:float(shares[j]) for j,t in enumerate(TICKERS)})
        ledger.append(record);prior_nav=nav
        month_end=i<len(dates)-1 and dates[i].month!=dates[i+1].month
        decide=(i==start) or (month_end and mode not in {"spy","qqq"})
        if decide and i+config.execution_delay<len(dates):
            weights=target_weights(i,ret,tri,config,mode)
            pending[i+config.execution_delay]=(i,weights.copy())
            decisions.append({"date":dates[i],"execution_date":dates[i+config.execution_delay],
                              **{"weight_"+t:float(weights[j]) for j,t in enumerate(TICKERS)}})
    return pd.DataFrame(ledger),pd.DataFrame(decisions),pd.DataFrame(orders,columns=["decision_date","execution_date","ticker","quantity","price","fee"])


def metrics(ledger):
    d=ledger;returns=d["return"].to_numpy();wealth=np.r_[float(d.prior_nav.iloc[0]),d.nav.to_numpy()]
    excess=returns-d.cash_return.to_numpy();sd=float(excess.std(ddof=1))
    elapsed=float(d.elapsed_days.sum()) if "elapsed_days" in d else (d.date.iloc[-1]-d.date.iloc[0]).days+1
    years=elapsed/365.25
    return {"total_return":float(wealth[-1]/wealth[0]-1),"cagr":float((wealth[-1]/wealth[0])**(1/years)-1),
            "excess_sharpe":float(excess.mean()/sd*np.sqrt(252)) if sd>1e-15 else None,
            "max_drawdown":float((wealth/np.maximum.accumulate(wealth)-1).min()),
            "annualized_gross_turnover":float(d.turnover.sum()/years),"total_cost":float(d.cost.sum()),
            "min_cash":float(d.cash.min()),"max_abs_bridge_error":float(d.bridge_error.abs().max())}
