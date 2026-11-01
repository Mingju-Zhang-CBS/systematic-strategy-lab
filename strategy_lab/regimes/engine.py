"""Next-session-close, self-financing total-return-unit accounts."""
import numpy as np
import pandas as pd
from .config import STRATEGIES


def targets(feature_frame, states, cfg):
    s = states.set_index("date")
    f = feature_frame.loc[s.index]
    sigma = f.volatility.to_numpy()
    scale = np.divide(cfg.target_vol, sigma, out=np.zeros_like(sigma), where=sigma > 0)
    scale = np.clip(scale, 0, 1)
    out = pd.DataFrame(index=s.index)
    out["buy_hold"] = 1.
    out["vol_hold"] = scale
    for kind in ("raw", "ema", "kalman"):
        out[kind+"_momentum"] = (f[kind+"_momentum"].to_numpy() > 0)*scale
    out["kalman_hmm"] = (out.kalman_momentum.to_numpy()
                           * (s.weighted_state_log_return.to_numpy() > 0)
                           * s.status.eq("ok").to_numpy())
    return out


def funded_trade(units, cash, price, target, cost_bps):
    values = [units, cash, price, target, cost_bps]
    if (not np.isfinite(values).all() or units < 0 or cash < -1e-8
            or price <= 0 or not 0 <= target <= 1 or not 0 <= cost_bps < 10000):
        raise ValueError("Invalid funded trade inputs")
    cost = cost_bps/10000
    risky = units*price
    pre = risky+cash
    desired = target*pre-risky
    delta = desired/(1+target*cost if desired >= 0 else 1-target*cost)
    fee = abs(delta)*cost
    new_units = units+delta/price
    new_cash = cash-delta-fee
    if new_cash < -1e-7 or new_units < -1e-9:
        raise ArithmeticError("Trade violates long-only cash funding")
    return max(0., new_units), max(0., new_cash), delta, fee


def backtest(prices, weights, cfg, strategy, cost_bps=5., cash_rate=0.):
    """Observe t, execute frozen fraction at t+1 close, earn it after that close."""
    if strategy not in STRATEGIES or not len(weights):
        raise ValueError("Known strategy and evaluation dates required")
    if (not np.isfinite([cash_rate, cost_bps]).all() or cash_rate < 0
            or not 0 <= cost_bps < 10000):
        raise ValueError("Nonnegative cash rate and valid cost required")
    if not prices.index.equals(weights.index) or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Prices and targets must share unique ordered dates")
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Finite positive prices required")
    if not np.isfinite(weights).all() or ((weights < 0) | (weights > 1)).any():
        raise ValueError("Targets must lie in [0,1]")
    cash = cfg.initial_nav; units = 0.; prior_nav = cash
    previous_price = float(prices.iloc[0]); previous_date = prices.index[0]
    pending = None
    ledger = []; trades = []; decisions = []
    for i, (date, price) in enumerate(prices.items()):
        price = float(price)
        days = (date-previous_date).days
        reserve_return = np.expm1(cash_rate*days/365.25)
        interest = cash*reserve_return
        held_weight = units*previous_price/prior_nav
        pnl = units*(price-previous_price)
        cash += interest
        pre = cash+units*price; fee = delta = 0.
        executed = ""
        if pending is not None:
            decision_date, target = pending
            units, cash, delta, fee = funded_trade(units, cash, price, target, cost_bps)
            executed = str(decision_date.date())
            if delta != 0:
                trades.append({"decision_date": executed, "execution_date": str(date.date()),
                               "model_unit_price": price, "quantity": delta/price,
                               "signed_notional": delta, "fee": fee, "target_weight": target})
        nav = units*price+cash
        bridge = nav-prior_nav-pnl-interest+fee
        if abs(bridge) > 1e-7 or cash < 0 or not 0 <= units*price/nav <= 1+1e-12:
            raise ArithmeticError("Account conservation or exposure failed")
        ledger.append({"date": str(date.date()), "prior_nav": prior_nav, "nav": nav,
                       "return": nav/prior_nav-1, "cash": cash, "units": units,
                       "model_unit_price": price, "security_pnl": pnl, "cash_interest": interest,
                       "cash_return": reserve_return, "fee": fee, "signed_notional": delta,
                       "turnover": abs(delta)/pre, "held_weight": held_weight,
                       "end_weight": units*price/nav, "bridge_error": bridge,
                       "executed_decision_date": executed})
        pending = None
        if strategy != "buy_hold" or i == 0:
            target = float(weights.iloc[i])
            can_execute = i+1 < len(prices)
            decisions.append({"decision_date": str(date.date()), "target_weight": target,
                              "execution_date": str(prices.index[i+1].date()) if can_execute else "",
                              "status": "scheduled" if can_execute else "not_executed_end_of_snapshot"})
            if can_execute:
                pending = date, target
        prior_nav = nav; previous_price = price; previous_date = date
    return (pd.DataFrame(ledger), pd.DataFrame(decisions),
            pd.DataFrame(trades, columns=["decision_date", "execution_date", "model_unit_price",
                                         "quantity", "signed_notional", "fee", "target_weight"]))


def metrics(ledger):
    if not len(ledger):
        raise ValueError("Nonempty ledger required")
    r = ledger["return"].to_numpy(); excess = r-ledger.cash_return.to_numpy()
    wealth = np.r_[1., np.cumprod(1+r)]
    years = len(r)/252
    vol = np.std(r, ddof=1)*np.sqrt(252) if len(r) > 1 else 0.
    sd = np.std(excess, ddof=1) if len(r) > 1 else 0.
    return {"observations": len(r), "total_return": float(wealth[-1]-1),
            "cagr": float(wealth[-1]**(1/years)-1), "annualized_volatility": float(vol),
            "excess_sharpe": float(excess.mean()/sd*np.sqrt(252)) if sd > 1e-15 else None,
            "max_drawdown": float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
            "annualized_turnover": float(ledger.turnover.sum()/years),
            "average_held_weight": float(ledger.held_weight.mean()),
            "average_end_weight": float(ledger.end_weight.mean()),
            "total_fees": float(ledger.fee.sum()), "min_cash": float(ledger.cash.min()),
            "max_bridge_error": float(ledger.bridge_error.abs().max())}


def paired_interval(differences, block, samples=2000, seed=42):
    """Noncircular moving-block bootstrap of the paired arithmetic return mean."""
    d = np.asarray(differences, float)
    n = len(d)
    if d.ndim != 1 or not np.isfinite(d).all() or not 1 <= block <= n or samples < 2:
        raise ValueError("Finite paired returns and valid block/sample counts required")
    whole, remainder = divmod(n, block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n-block+1, size=(samples, whole+(remainder > 0)))
    cumulative = np.r_[0., np.cumsum(d)]
    sums = (cumulative[starts[:, :whole]+block]-cumulative[starts[:, :whole]]).sum(axis=1)
    if remainder:
        sums += cumulative[starts[:, -1]+remainder]-cumulative[starts[:, -1]]
    low, high = np.quantile(sums/n*252, [.025, .975])
    return {"block_sessions": block, "bootstrap_samples": samples,
            "annualized_mean_difference": float(d.mean()*252),
            "lower_95": float(low), "upper_95": float(high)}
