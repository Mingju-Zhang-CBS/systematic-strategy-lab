"""Strict adjusted OHLC bars and invented envelopes around unchanged parent closes."""
import numpy as np
import pandas as pd
from ..data import synthetic_prices,validate_prices
from .config import ASSETS,BreakoutConfig

FIELDS=("adjusted_open","adjusted_high","adjusted_low","adjusted_close")


def validate_bars(frame,expected_sessions=None):
    if set(frame.columns)!={"date","ticker",*FIELDS}:
        raise ValueError("Exactly date,ticker,adjusted_open,adjusted_high,adjusted_low,adjusted_close required")
    d=frame.copy();d["date"]=pd.to_datetime(d.date,errors="raise")
    close=validate_prices(d[["date","ticker","adjusted_close"]],expected_sessions)
    d["date"]=close.date.to_numpy()
    for field in FIELDS:d[field]=pd.to_numeric(d[field],errors="raise")
    x=d[list(FIELDS)].to_numpy()
    if not np.isfinite(x).all() or (x<=0).any():raise ValueError("Positive finite OHLC required")
    epsilon=1e-12*np.max(x,axis=1)
    if ((d.adjusted_high+epsilon<d[["adjusted_open","adjusted_close"]].max(axis=1)).any()
            or (d.adjusted_low-epsilon>d[["adjusted_open","adjusted_close"]].min(axis=1)).any()
            or (d.adjusted_high<d.adjusted_low).any()):raise ValueError("OHLC containment fails")
    return d.reset_index(drop=True)


def synthetic_bars(cfg=BreakoutConfig()):
    cfg.validate();d=synthetic_prices();rng=np.random.default_rng(cfg.envelope_seed);rows=[]
    for asset in ASSETS:
        series=d[d.ticker.eq(asset)].copy();close=series.adjusted_close.to_numpy()
        previous=np.r_[close[0],close[:-1]]
        opening=previous*np.exp(rng.normal(0,.003,len(close)))
        high=np.maximum(opening,close)*np.exp(np.abs(rng.normal(0,.005,len(close))))
        low=np.minimum(opening,close)*np.exp(-np.abs(rng.normal(0,.005,len(close))))
        series["adjusted_open"]=opening;series["adjusted_high"]=high;series["adjusted_low"]=low
        rows.append(series)
    return validate_bars(pd.concat(rows,ignore_index=True).sort_values(["date","ticker"]).reset_index(drop=True))
