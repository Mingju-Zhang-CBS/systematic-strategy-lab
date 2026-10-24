"""Past-only allocation decisions, explicit NAV posting and funded fee accounting."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .real_data import FUNDS, RISKY, validate_nav


@dataclass(frozen=True)
class RealConfig:
    lookback: int = 252
    skip: int = 21
    covariance: int = 126
    vol_target: float = .10
    asset_cap: float = .50
    risky_cap: float = .99
    publication_lag: int = 1
    execution_delay: int = 2
    cost_bps: float = 3.
    initial_nav: float = 100000.
    start: str = "2004-07-01"

    def validate(self):
        if self.execution_delay <= self.publication_lag or self.publication_lag < 1:
            raise ValueError("Request must follow a complete assumed publication session")
        if not 0 <= self.cost_bps <= 100 or self.initial_nav <= 0:
            raise ValueError("Invalid capital or proportional friction")
        if not 0 < self.skip < self.lookback or self.covariance < 2:
            raise ValueError("Invalid trailing signal windows")
        if not 0 < self.asset_cap <= 1 or not 0 < self.risky_cap <= 1 or self.vol_target <= 0:
            raise ValueError("Invalid target limits")


def target_weights(values, returns, t, mode, cfg):
    """Read observations at or before t; whole-percent targets, no leverage."""
    if mode in ("C_buy_hold", "G_buy_hold"):
        weights = np.zeros(5)
        weights[FUNDS.index(mode[0])] = 1.
        return weights, np.full(4, np.nan), 1.
    if mode not in ("momentum", "risk_matched_static"):
        raise ValueError("Unknown strategy")
    momentum = values[t-cfg.skip, 1:] / values[t-cfg.lookback, 1:] - 1
    selected = momentum > 0 if mode == "momentum" else np.ones(4, dtype=bool)
    risky = np.zeros(4)
    if selected.any():
        risky[selected] = min(cfg.asset_cap, cfg.risky_cap / selected.sum())
    cov = np.cov(returns[t-cfg.covariance+1:t+1, 1:], rowvar=False, ddof=1)
    volatility = float(np.sqrt(max(0., risky @ cov @ risky) * 252))
    scale = min(1., cfg.vol_target / volatility) if volatility > 0 else 1.
    risky = np.floor(risky * scale * 100 + 1e-10) / 100
    return np.r_[1-risky.sum(), risky], momentum, scale


def rebalance_units(units, prices, weights, cost_bps):
    """Solve V_after + bps * sum(abs(new dollar holdings - old)) = V_before."""
    old = np.asarray(units, dtype=float) * prices
    weights = np.asarray(weights, dtype=float)
    if (weights < -1e-12).any() or not np.isclose(weights.sum(), 1.):
        raise ValueError("Targets must be fully funded and sum to one")
    before = float(old.sum())
    rate = cost_bps / 10000
    if not 0 <= rate <= .01 or before <= 0:
        raise ValueError("Invalid funded rebalance")
    if np.allclose(old, weights*before, rtol=0, atol=1e-9):
        return np.asarray(units, dtype=float).copy(), 0., 0., np.zeros_like(old)
    if rate == 0:
        dollars=weights*before-old
        return weights*before/prices, 0., float(np.abs(dollars).sum()), dollars
    lo, hi = 0., before
    for _ in range(60):
        after = (lo+hi)/2
        if after + rate * np.abs(weights*after-old).sum() > before:
            hi = after
        else:
            lo = after
    after = (lo+hi)/2
    dollars = weights*after-old
    gross = float(np.abs(dollars).sum())
    fee = rate*gross
    new_units = weights*after/prices
    if not np.isclose(new_units @ prices + fee, before, atol=1e-8, rtol=0):
        raise ArithmeticError("Funded rebalance failed to conserve value")
    return new_units, fee, gross, dollars


def et_clock(day, time):
    return pd.Timestamp(f"{pd.Timestamp(day).date()} {time}").tz_localize("America/New_York").isoformat()


def backtest_real(data, cfg=RealConfig(), mode="momentum"):
    cfg.validate()
    data = validate_nav(data)
    dates = pd.DatetimeIndex(data.date)
    prices = data[list(FUNDS)].to_numpy(dtype=float)
    returns = np.vstack([np.zeros(5), prices[1:]/prices[:-1]-1])
    start = int(dates.searchsorted(pd.Timestamp(cfg.start)))
    if start < max(cfg.lookback, cfg.covariance) or start >= len(data):
        raise ValueError("Insufficient trailing data or evaluation observations")
    month = dates.to_period("M")
    units = np.zeros(5)
    units[0] = cfg.initial_nav/prices[start-1, 0]
    previous = cfg.initial_nav
    pending = {}
    ledgers, decisions, orders = [], [], []
    transfers = {}
    for t in range(start, len(data)):
        before_units = units.copy()
        pnl = float(before_units @ (prices[t]-prices[t-1]))
        pretrade = float(before_units @ prices[t])
        fee, gross = 0., 0.
        decision_id = ""
        if t in pending:
            d = pending.pop(t)
            w = d["weights"]
            units, fee, gross, dollars = rebalance_units(units, prices[t], w, cfg.cost_bps)
            decision_id = d["id"]
            if gross > 1e-7:
                key = str(month[t])
                transfers[key] = transfers.get(key, 0) + 1
                if transfers[key] > 2:
                    raise ArithmeticError("More than two modeled transfers in a posting month")
            for j, fund in enumerate(FUNDS):
                orders.append({"decision_id": d["id"], "posting_date": str(dates[t].date()),
                               "fund": fund, "units_before": float(before_units[j]),
                               "units_after": float(units[j]), "posting_nav": float(prices[t,j]),
                               "traded_dollars": float(dollars[j]), "target_weight": float(w[j]),
                               "total_transfer_fee": fee, "value_before": pretrade,
                               "value_after": float(units @ prices[t])})
        nav = float(units @ prices[t])
        bridge = nav - (previous+pnl-fee)
        if abs(bridge) > 1e-7:
            raise ArithmeticError("Daily NAV bridge failed")
        row = {"date": str(dates[t].date()), "nav": nav, "prior_nav": previous,
               "return": nav/previous-1, "reserve_return": float(returns[t,0]),
               "price_income_pnl": pnl, "fee": fee, "gross_traded": gross,
               "turnover": gross/pretrade, "bridge_error": bridge,
               "cash_dividend_added": 0., "extra_operating_expense": 0.,
               "decision_id": decision_id}
        row.update({f"units_{f}": float(units[j]) for j,f in enumerate(FUNDS)})
        row.update({f"weight_{f}": float(units[j]*prices[t,j]/nav) for j,f in enumerate(FUNDS)})
        ledgers.append(row)
        previous = nav
        is_first = t == start
        month_end = t < len(data)-1 and month[t] != month[t+1]
        if not (is_first or month_end) or (mode.endswith("buy_hold") and not is_first):
            continue
        w, mom, scale = target_weights(prices, returns, t, mode, cfg)
        available = t+cfg.publication_lag
        execution = t+cfg.execution_delay
        ident = f"{mode}:{dates[t].date()}"
        executable = execution < len(data)
        decision = {"decision_id": ident, "observation_date": str(dates[t].date()),
                    "max_feature_date": str(dates[t].date()),
                    "assumed_available_after": et_clock(dates[available], "23:59:59") if available < len(data) else "beyond_snapshot",
                    "request_at": et_clock(dates[execution], "11:00:00") if executable else "beyond_snapshot",
                    "posting_date": str(dates[execution].date()) if executable else "beyond_snapshot",
                    "delay_sessions": cfg.execution_delay, "volatility_scale": scale,
                    "status": "scheduled" if executable else "not_executed_end_of_snapshot"}
        decision.update({f"target_{f}": float(w[j]) for j,f in enumerate(FUNDS)})
        decision.update({f"momentum_{f}": float(mom[j]) if np.isfinite(mom[j]) else None for j,f in enumerate(RISKY)})
        decisions.append(decision)
        if executable:
            if execution in pending:
                raise ArithmeticError("Order collision")
            pending[execution] = {"id": ident, "weights": w.copy()}
    return pd.DataFrame(ledgers), pd.DataFrame(decisions), pd.DataFrame(orders)


def real_metrics(ledger):
    r = ledger["return"].to_numpy()
    g = ledger.reserve_return.to_numpy()
    excess = r-g
    wealth = np.r_[1., np.cumprod(1+r)]
    years = len(r)/252
    std = np.std(excess, ddof=1) if len(r)>1 else 0.
    return {"observations": len(r), "total_return": float(wealth[-1]-1),
            "annualized_return": float(wealth[-1]**(1/years)-1),
            "annualized_volatility": float(np.std(r, ddof=1)*np.sqrt(252)) if len(r)>1 else 0.,
            "excess_sharpe": float(np.mean(excess)/std*np.sqrt(252)) if std>1e-14 else None,
            "max_drawdown": float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
            "annual_gross_turnover": float(ledger.turnover.sum()/years),
            "total_cost": float(ledger.fee.sum()),
            "max_abs_bridge_error": float(ledger.bridge_error.abs().max()),
            "mean_reserve_weight": float(ledger.weight_G.mean())}


def paired_inference(momentum, control, block=20, replications=2000, seed=20261023):
    if not np.array_equal(momentum.date.to_numpy(), control.date.to_numpy()):
        raise ValueError("Paired inference requires identical dates")
    delta = np.log1p(momentum["return"].to_numpy())-np.log1p(control["return"].to_numpy())
    n = len(delta)
    if not 1 <= block <= n or replications < 2:
        raise ValueError("Invalid moving-block bootstrap")
    rng = np.random.default_rng(seed)
    # Non-circular overlapping blocks: no fabricated last-to-first adjacency.
    blocks = np.lib.stride_tricks.sliding_window_view(delta, block)
    samples = np.empty(replications)
    for i in range(replications):
        starts = rng.integers(0, len(blocks), size=int(np.ceil(n/block)))
        samples[i] = blocks[starts].ravel()[:n].mean()*252
    low, high = np.quantile(samples, [.025, .975])
    return {"paired_observations": n, "annualized_log_return_difference": float(delta.mean()*252),
            "ci95_low": float(low), "ci95_high": float(high), "includes_zero": bool(low<=0<=high),
            "block_sessions": block, "replications": replications, "seed": seed,
            "interpretation": "Descriptive paired historical inference; not a test of prospective alpha."}
