"""Publication-clocked cash opportunity cost; never changes strategy orders."""
import numpy as np
import pandas as pd


def effr_reference(observations, release_time="14:45"):
    """Infer a scheduled next-business-day clock from effective-date observations.

    This is current-vintage EFFR, not an archived publication feed. The next
    effective date is a calendar proxy. The last observation has no inferred
    release date and is explicitly omitted, never backfilled into earlier dates.
    """
    x=observations[['effectiveDate','percentRate']].copy()
    x['effective_date']=pd.to_datetime(x.effectiveDate).dt.normalize()
    x=x.sort_values('effective_date').reset_index(drop=True)
    if x.effective_date.duplicated().any() or not np.isfinite(x.percentRate).all():
        raise ValueError('Unique finite EFFR observations required')
    release_dates=x.effective_date.shift(-1).iloc[:-1]
    clock=pd.to_datetime(release_dates.dt.strftime('%Y-%m-%d')+' '+release_time)
    available=clock.dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    return pd.DataFrame({'effective_date':x.effective_date.iloc[:-1],
                         'available_at':available,'annual_percent':x.percentRate.iloc[:-1]})


def cash_benchmark(sessions, reference, initial_cash=100000.):
    """ACT/360 proxy, using only the rate known at each interval's start.

    First interval starts at the first supplied open, then close-to-close.
    A weekend contributes actual elapsed calendar time. The strategy's idle
    cash remains unremunerated under the original frozen account convention.
    """
    s=sessions[['session','open','close']].copy()
    s['open']=pd.to_datetime(s.open,utc=True);s['close']=pd.to_datetime(s.close,utc=True)
    r=reference.copy();r['available_at']=pd.to_datetime(r.available_at,utc=True)
    if (s.empty or not s.close.is_monotonic_increasing or (s.close<=s.open).any()
            or s.session.duplicated().any() or initial_cash<=0
            or not r.available_at.is_monotonic_increasing or r.available_at.duplicated().any()
            or not np.isfinite(r.annual_percent).all()):
        raise ValueError('Ordered unique sessions and publication-clocked finite rates required')
    starts=s.close.shift(1);starts.iloc[0]=s.open.iloc[0]
    positions=np.searchsorted(r.available_at.to_numpy(dtype='datetime64[ns]'),
                              starts.to_numpy(dtype='datetime64[ns]'),side='right')-1
    if (positions<0).any():raise ValueError('Cash reference does not cover the initial information clock')
    known=r.iloc[positions].reset_index(drop=True)
    # ACT/360 calendar-day accrual must not lose/gain an hour over a DST
    # weekend. Intraday fractions use New York wall-clock times.
    end_wall=s.close.dt.tz_convert('America/New_York').dt.tz_localize(None).reset_index(drop=True)
    start_wall=starts.dt.tz_convert('America/New_York').dt.tz_localize(None).reset_index(drop=True)
    elapsed=(end_wall-start_wall).dt.total_seconds()/(360*86400)
    growth=1+known.annual_percent.to_numpy()/100*elapsed.to_numpy()
    result=s.reset_index(drop=True).copy();result['interval_start']=starts.to_numpy()
    result['rate_effective_date']=known.effective_date.to_numpy()
    result['rate_available_at']=known.available_at.to_numpy()
    result['annual_percent']=known.annual_percent.to_numpy()
    result['elapsed_calendar_days']=elapsed.to_numpy()*360
    result['benchmark_return']=growth-1
    result['benchmark_cash']=initial_cash*np.cumprod(growth)
    return result
