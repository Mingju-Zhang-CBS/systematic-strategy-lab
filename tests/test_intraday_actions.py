import pandas as pd
import pytest
from strategy_lab.intraday.actions import action_table


def fixture():
    d=pd.DataFrame({'permno':[1,1,1],'dlycaldt':['2020-01-02','2020-01-03','2020-01-06'],
        'dlyprc':[100.,99.,49.5],'dlyprevprc':[100.,100.,99.], 'dlyret':[0.,0.,0.],
        'dlyorddivamt':[0.,1.,0.],'dlynonorddivamt':[0.,0.,0.],'dlydistretflg':['NO','C1','S1']})
    e=pd.DataFrame({'permno':[1,1],'disexdt':['2020-01-03','2020-01-06'],'disseqnbr':[1,1],
        'disdeclaredt':['2020-01-01','2020-01-02'],'disdivamt':[1.,0.],'disfacshr':[0.,1.],
        'distype':['CD','FRS'],'dispaymenttype':['USD','SHR'],'disorigcurtype':['USD','N/A']})
    n=pd.DataFrame({'permno':[1],'ticker':['SYNTH'],'secinfostartdt':['2019-01-01'],'secinfoenddt':['2021-12-31']})
    return d,e,n


def test_cash_and_split_units_reconcile_total_return():
    d,e,n=fixture();a,issues=action_table(d,e,n)
    assert issues.empty and a.source_ready.all()
    assert a.cash_dividend.to_list()==[0.,1.,0.]
    assert a.split.to_list()==[1.,1.,2.]


def test_missing_or_same_day_declaration_is_not_assumed_known():
    d,e,n=fixture();e.loc[0,'disdeclaredt']=None;e.loc[1,'disdeclaredt']=e.loc[1,'disexdt']
    a,issues=action_table(d,e,n)
    assert issues.reason.to_list()==['action_publication_clock_unknown']*2
    assert not a.source_ready.iloc[1:].any()
    assert a.action_available_at.iloc[1:].isna().all()


def test_nonzero_cash_without_event_and_conflicting_identity_rejected():
    d,e,n=fixture();_,issues=action_table(d,e.iloc[1:],n)
    assert 'distribution_record_missing' in issues.reason.to_list()
    with pytest.raises(ValueError):action_table(d,e,pd.concat([n,n]))


def test_future_events_and_identity_do_not_change_earlier_adjustments():
    d,e,n=fixture();a,_=action_table(d,e,n)
    future=e.iloc[-1:].copy();future['disexdt']='2020-12-01';future['disdeclaredt']='2020-11-20'
    future_identity=n.iloc[:1].copy();future_identity['secinfostartdt']='2022-01-01';future_identity['secinfoenddt']='2025-01-01'
    b,_=action_table(d,pd.concat([e,future]),pd.concat([n,future_identity]))
    pd.testing.assert_frame_equal(a,b)
