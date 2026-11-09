"""Fixed-universe dual-momentum comparisons on an explicit daily ledger."""

import numpy as np
import pandas as pd

PAIRS = (("SPY", "EFA"), ("HYG", "LQD"), ("VNQ", "REM"), ("GLD", "TLT"))
ASSETS = tuple(ticker for pair in PAIRS for ticker in pair)
COLUMNS = (*ASSETS, "RF")
ARMS = ("relative", "trailing36", "dual", "same_gate_equal")
START = "2012-01"
END = "2026-06"
COSTS_BPS = (0, 5, 10, 20)


def monthly_marks(daily):
    """Compound realized decimal returns by calendar month."""
    return (1 + daily).groupby(daily.index.to_period("M")).prod() - 1


def target_weights(monthly):
    """Targets indexed by signal month, with no same-month gate in trailing exposure."""
    if list(monthly.columns) != list(COLUMNS) or not isinstance(monthly.index, pd.PeriodIndex):
        raise ValueError("Expected the eight ordered ETF columns and RF on monthly periods")
    if not monthly.index.equals(pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")):
        raise ValueError("Signal months must be unique, ordered and consecutive")
    if not np.isfinite(monthly).all().all() or (monthly <= -1).any().any():
        raise ValueError("Incomplete or invalid signal returns")

    trailing = (1 + monthly).rolling(12).apply(np.prod, raw=True) - 1
    trailing = trailing.dropna()
    targets = {arm: pd.DataFrame(0.0, index=trailing.index, columns=COLUMNS) for arm in ARMS}
    for left, right in PAIRS:
        winner = pd.Series(np.where(trailing[left] >= trailing[right], left, right), index=trailing.index)
        gate = trailing[[left, right]].max(axis=1).gt(trailing["RF"])
        history = gate.shift(1).rolling(36).mean()
        for ticker in (left, right):
            relative = 0.25 * winner.eq(ticker)
            targets["relative"][ticker] = relative
            targets["trailing36"][ticker] = relative * history
            targets["dual"][ticker] = relative * gate
            targets["same_gate_equal"][ticker] = 0.125 * gate
    for target in targets.values():
        target["RF"] = 1 - target[list(ASSETS)].sum(axis=1, skipna=False)
    return targets


def session_returns(etf_returns, monthly_rf):
    """Distribute the homework's realized monthly cash benchmark over its sessions."""
    rf = monthly_rf.reindex(etf_returns.index.to_period("M"))
    rf.index = etf_returns.index
    if rf.isna().any() or not np.isfinite(rf).all() or (rf <= -1).any():
        raise ValueError("Missing or invalid monthly cash proxy")
    sessions = rf.groupby(rf.index.to_period("M")).transform("size")
    return etf_returns.assign(RF=np.expm1(np.log1p(rf) / sessions)).loc[:, list(COLUMNS)]


def rebalance(values, weights, cost_rate):
    """Fund trades and fees from the same account using ETF dollar buys plus sells."""
    wealth = values.sum()
    if not cost_rate:
        post_fee = wealth
    else:
        low, high = 0.0, wealth
        for _ in range(48):
            trial = (low + high) / 2
            turnover = np.abs(trial * weights[:-1] - values[:-1]).sum()
            if trial + cost_rate * turnover > wealth:
                high = trial
            else:
                low = trial
        post_fee = (low + high) / 2
    positions = post_fee * weights
    traded = np.abs(positions[:-1] - values[:-1]).sum()
    fee = cost_rate * traded
    if not np.isclose(positions.sum() + fee, wealth, rtol=1e-12, atol=1e-14):
        raise ArithmeticError("Rebalance is not self-financing")
    return positions, traded / wealth, fee / wealth


def simulate(daily, traded_closes, targets, cost_bps, start=START, end=END):
    """Mark old holdings through the execution close, then execute new targets."""
    if (
        not isinstance(daily.index, pd.DatetimeIndex)
        or not daily.index.is_unique
        or not daily.index.is_monotonic_increasing
        or list(daily.columns) != list(COLUMNS)
        or not np.isfinite(daily).all().all()
        or (daily <= -1).any().any()
    ):
        raise ValueError("Expected dense, ordered daily decimal returns")
    if not 0 <= cost_bps < 10_000:
        raise ValueError("Invalid one-way cost")
    periods = pd.period_range(start, end, freq="M")
    window = daily.loc[str(periods[0]):str(periods[-1])]
    first_sessions = window.groupby(window.index.to_period("M")).head(1).index
    if not first_sessions.to_period("M").equals(periods):
        raise ValueError("Incomplete execution months")
    execution_targets = targets.reindex(periods - 1)
    if (
        list(execution_targets.columns) != list(COLUMNS)
        or not np.isfinite(execution_targets).all().all()
        or (execution_targets < 0).any().any()
        or not np.allclose(execution_targets.sum(axis=1), 1)
    ):
        raise ValueError("Missing or invalid prior-month target")
    execution_targets.index = first_sessions
    quotes = traded_closes.reindex(index=first_sessions, columns=list(ASSETS))
    if not np.isfinite(quotes).all().all() or (quotes <= 0).any().any():
        raise ValueError("An ETF has no valid traded close on a scheduled execution date")

    positions = np.zeros(len(COLUMNS))
    positions[-1] = 1.0
    cost_rate = cost_bps / 10_000
    rows = []
    orders = dict(zip(first_sessions, execution_targets.to_numpy(dtype=float), strict=True))
    for date, returns in zip(window.index, window.to_numpy(dtype=float), strict=True):
        prior_nav = positions.sum()
        positions *= 1 + returns
        turnover, fee = 0.0, 0.0
        if date in orders:
            positions, turnover, fee = rebalance(positions, orders[date], cost_rate)
        nav = positions.sum()
        rows.append((nav, nav / prior_nav - 1, positions[-1] / nav, turnover, fee))
    return pd.DataFrame(rows, index=window.index, columns=["nav", "return", "cash", "turnover", "fee"])


def max_drawdown(nav):
    return float((nav / nav.cummax().clip(lower=1.0) - 1).min())


def metrics(ledger, monthly_rf):
    monthly = monthly_marks(ledger["return"])
    excess = monthly - monthly_rf.reindex(monthly.index)
    return {
        "cagr": float(ledger.nav.iloc[-1] ** (12 / len(monthly)) - 1),
        "daily_max_drawdown": max_drawdown(ledger.nav),
        "monthly_max_drawdown": max_drawdown((1 + monthly).cumprod()),
        "annualized_vol": float(monthly.std() * np.sqrt(12)),
        "monthly_excess_sharpe": float(excess.mean() / excess.std() * np.sqrt(12)) if excess.std() else None,
        "average_daily_cash": float(ledger.cash.mean()),
        "annualized_gross_etf_turnover": float(ledger.turnover.sum() * 12 / len(monthly)),
        "annualized_fees": float(ledger.fee.sum() * 12 / len(monthly)),
    }


def paired_log_growth(left, right, block=12, draws=3_000, seed=20261109):
    """Paired moving-block interval for annualized mean monthly log-return gap."""
    if not left.index.equals(right.index) or len(left) < block:
        raise ValueError("Paired inference requires an identical calendar and enough months")
    diff = (np.log1p(left) - np.log1p(right)).to_numpy()
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(diff) - block + 1, size=(draws, -(-len(diff) // block)))
    selection = (starts[:, :, None] + np.arange(block)).reshape(draws, -1)[:, :len(diff)]
    low, high = np.quantile(12 * diff[selection].mean(axis=1), [0.025, 0.975])
    return {"estimate": float(12 * diff.mean()), "low": float(low), "high": float(high)}
