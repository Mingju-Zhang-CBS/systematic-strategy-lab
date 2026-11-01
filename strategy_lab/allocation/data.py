"""Five-asset adjusted-close contract and an independently invented fixture."""
import numpy as np
import pandas as pd
from .config import ASSETS


def validate_prices(frame, expected_sessions=None):
    if set(frame.columns) != {"date","ticker","adjusted_close"} or frame.empty:
        raise ValueError("Nonempty date,ticker,adjusted_close table required")
    d=frame.copy();d["date"]=pd.to_datetime(d.date,errors="raise")
    if d.date.isna().any() or d.date.dt.tz is not None or not d.date.eq(d.date.dt.normalize()).all():
        raise ValueError("Midnight, timezone-naive session dates required")
    if set(d.ticker)!=set(ASSETS) or d.duplicated(["date","ticker"]).any():
        raise ValueError("Exactly SPY,EFA,IEF,GLD,DBC, without duplicate keys")
    if not d.sort_values(["date","ticker"]).reset_index(drop=True).equals(d.reset_index(drop=True)):
        raise ValueError("Input must be ordered by date,ticker")
    d["adjusted_close"]=pd.to_numeric(d.adjusted_close,errors="raise")
    if not np.isfinite(d.adjusted_close).all() or (d.adjusted_close<=0).any():
        raise ValueError("Positive finite prices required")
    if not d.groupby("date").size().eq(len(ASSETS)).all():
        raise ValueError("Every asset required on every declared session")
    if expected_sessions is not None:
        expected=pd.DatetimeIndex(pd.to_datetime(expected_sessions))
        if expected.has_duplicates or expected.hasnans or not expected.is_monotonic_increasing:
            raise ValueError("Expected sessions must be ordered and unique")
        if not pd.DatetimeIndex(d.date.unique()).equals(expected):
            raise ValueError("Data coverage differs from expected session calendar")
    return d.reset_index(drop=True)


def synthetic_prices(seed=20261102):
    """Stylized factors, changing drifts/correlations; not actual ETF history."""
    dates=pd.bdate_range("2009-01-01","2025-12-31");rng=np.random.default_rng(seed)
    n=len(dates);phase=np.sin(np.arange(n)/200)
    factors=rng.normal(size=(n,3))
    loads=np.array([[.010,.001,.001],[.011,.002,.003],[-.001,.003,.001],
                    [.001,-.001,.009],[.005,-.002,.009]])
    drifts=np.array([.00025,.00012,.00007,.00011,.00004])
    sensitivity=np.array([.00035,.0003,-.00006,.00015,-.0002])
    logreturns=factors@loads.T+rng.normal(0,.003,(n,5))+drifts+phase[:,None]*sensitivity
    levels=100*np.exp(np.cumsum(logreturns,axis=0))
    rows=[{"date":date,"ticker":asset,"adjusted_close":levels[i,j]}
          for i,date in enumerate(dates) for j,asset in enumerate(ASSETS)]
    return validate_prices(pd.DataFrame(rows).sort_values(["date","ticker"]).reset_index(drop=True))


def wide_prices(frame):
    return validate_prices(frame).pivot(index="date",columns="ticker",values="adjusted_close").reindex(columns=ASSETS)
