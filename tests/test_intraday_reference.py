import numpy as np
import pandas as pd
import pytest
from strategy_lab.intraday.reference import effr_reference,cash_benchmark


def observations():
    return pd.DataFrame({'effectiveDate':['2023-01-05','2023-01-06','2023-01-09','2023-01-10'],
                         'percentRate':[3.6,4.,5.,6.]})


def sessions():
    return pd.DataFrame({'session':['2023-01-06','2023-01-09'],
        'open':['2023-01-06T14:30Z','2023-01-09T14:30Z'],
        'close':['2023-01-06T21:00Z','2023-01-09T21:00Z']})


def test_same_day_and_weekend_clock_are_not_looked_ahead():
    r=effr_reference(observations())
    assert r.available_at.iloc[0]==pd.Timestamp('2023-01-06T19:45Z')
    s=sessions().iloc[1:]
    b=cash_benchmark(s,r)
    # Monday morning still uses the Thursday-effective rate. Friday's final
    # current-vintage rate is not assumed available before Monday 14:45 ET.
    assert b.annual_percent.iloc[0]==3.6


def test_cash_compounding_uses_elapsed_days_and_interval_start():
    s=sessions();s.loc[0,'open']='2023-01-06T20:00Z'
    b=cash_benchmark(s,effr_reference(observations()))
    expected=100000*(1+.036*(1/24)/360)*(1+.036*3/360)
    assert b.benchmark_cash.iloc[-1]==pytest.approx(expected)
    assert b.elapsed_calendar_days.iloc[-1]==3


def test_future_rate_perturbation_does_not_change_prior_reference():
    o=observations();s=sessions();s.loc[0,'open']='2023-01-06T20:00Z'
    a=cash_benchmark(s,effr_reference(o));o.loc[1:,'percentRate']=99
    b=cash_benchmark(s,effr_reference(o))
    pd.testing.assert_frame_equal(a,b)


def test_missing_initial_reference_and_duplicate_dates_rejected():
    with pytest.raises(ValueError):cash_benchmark(sessions(),effr_reference(observations()))
    o=observations();o.loc[1,'effectiveDate']=o.loc[0,'effectiveDate']
    with pytest.raises(ValueError):effr_reference(o)


def test_dst_release_clock_follows_new_york_time():
    o=pd.DataFrame({'effectiveDate':['2023-03-09','2023-03-10','2023-03-13'],
                    'percentRate':[4.,4.,4.]})
    r=effr_reference(o)
    assert (r.available_at.dt.hour.to_list())==[19,18]


def test_act360_weekend_is_three_calendar_days_across_dst():
    o=pd.DataFrame({'effectiveDate':['2023-03-08','2023-03-09','2023-03-10','2023-03-13'],
                    'percentRate':[4.,4.,4.,4.]})
    s=pd.DataFrame({'session':['2023-03-10','2023-03-13'],
        'open':['2023-03-10T14:30Z','2023-03-13T13:30Z'],
        'close':['2023-03-10T21:00Z','2023-03-13T20:00Z']})
    b=cash_benchmark(s,effr_reference(o))
    assert b.elapsed_calendar_days.iloc[-1]==3
