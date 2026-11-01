"""Strict adjusted-close input; no automatic missing-date deletion or filling."""
import numpy as np
import pandas as pd

ASSETS = ("SPY", "QQQ")


def validate_prices(frame, expected_sessions=None):
    required = {"date", "ticker", "adjusted_close"}
    if set(frame.columns) != required:
        raise ValueError("Exactly date,ticker,adjusted_close required")
    d = frame.copy()
    d["date"] = pd.to_datetime(d.date, errors="raise")
    if (d.empty or d.date.isna().any() or d.date.dt.tz is not None
            or not d.date.eq(d.date.dt.normalize()).all()):
        raise ValueError("Nonempty, midnight, timezone-naive session dates required")
    if set(d.ticker) != set(ASSETS) or d.duplicated(["date", "ticker"]).any():
        raise ValueError("SPY and QQQ required, without duplicate keys")
    if not d.sort_values(["date", "ticker"]).reset_index(drop=True).equals(d.reset_index(drop=True)):
        raise ValueError("Input must be ordered by date,ticker")
    d["adjusted_close"] = pd.to_numeric(d.adjusted_close, errors="raise")
    if not np.isfinite(d.adjusted_close).all() or (d.adjusted_close <= 0).any():
        raise ValueError("Finite positive prices required")
    if not d.groupby("date").size().eq(2).all():
        raise ValueError("Both assets required on every session")
    if expected_sessions is not None:
        expected = pd.DatetimeIndex(pd.to_datetime(expected_sessions))
        if expected.has_duplicates or not expected.is_monotonic_increasing or expected.hasnans:
            raise ValueError("Expected sessions must be unique, ordered and nonmissing")
        actual = pd.DatetimeIndex(d.date.unique())
        if not actual.equals(expected):
            raise ValueError("Price dates differ from supplied expected sessions")
    return d.reset_index(drop=True)


def synthetic_prices(seed=20261101):
    """Invented business-day observations. No historical holiday/fill claims."""
    dates = pd.bdate_range("2009-01-01", "2025-12-31")
    rng = np.random.default_rng(seed)
    hidden = np.empty(len(dates), dtype=int)
    hidden[0] = 1
    transition = np.array([[.97, .025, .005], [.015, .97, .015], [.005, .035, .96]])
    for i in range(1, len(dates)):
        hidden[i] = rng.choice(3, p=transition[hidden[i-1]])
    mean = np.array([-.0006, .0001, .0007])[hidden]
    sigma = np.array([.018, .007, .011])[hidden]
    shared = rng.normal(size=len(dates))
    rows = []
    for asset, loading in (("SPY", 1.), ("QQQ", 1.25)):
        shocks = .8*shared + .6*rng.normal(size=len(dates))
        logret = loading*(mean + sigma*shocks)
        prices = 100*np.exp(np.cumsum(logret))
        rows.extend({"date": date, "ticker": asset, "adjusted_close": float(p)}
                    for date, p in zip(dates, prices))
    return validate_prices(pd.DataFrame(rows).sort_values(["date", "ticker"]))
