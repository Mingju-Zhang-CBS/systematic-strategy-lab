import pandas as pd
from strategy_lab.intraday.demo import fixture
from strategy_lab.intraday.engine import Config,backtest
from strategy_lab.intraday.reconcile import reconcile_ledger


def test_independent_reconstruction_and_corruption_detection():
    b,q=fixture();d,o,_=backtest(b,q)
    _,a=reconcile_ledger(d,o,b,q,Config())
    assert a['cash_and_position_match'] and a['equity_matches_last_mark']
    assert a['bad_fill_times']==a['bad_quote_price_or_capacity']==a['bad_fee_calculations']==0
    changed=d.copy();changed.loc[0,'cash']+=10
    _,a=reconcile_ledger(changed,o,b,q,Config())
    assert not a['cash_and_position_match']


def test_missing_exit_retains_risk_in_independent_audit():
    b,q=fixture();d,o,_=backtest(b,q);first=d.session.iloc[0]
    close=b.loc[b.session_open.dt.strftime('%Y-%m-%d').eq(first),'session_close'].iloc[0]
    q=q.loc[~q.quote_time.between(close-pd.Timedelta(seconds=59),close)]
    d,o,_=backtest(b,q);_,a=reconcile_ledger(d,o,b,q,Config())
    assert a['stopped_with_retained_risk'] and a['remaining_shares']!=0
    assert a['cash_and_position_match'] and a['equity_matches_last_mark']


def test_no_trades_is_a_valid_cash_account():
    b,q=fixture();b['close']=b.open_price;b['dollar_volume']=b.volume*b.open_price
    d,o,_=backtest(b,q);_,a=reconcile_ledger(d,o,b,q,Config())
    assert a['cash_and_position_match'] and a['remaining_shares']==0


def test_scaled_funding_is_recomputed_without_treating_zero_quantity_as_a_sell():
    b,q=fixture();d,o,_=backtest(b,q,'vol_scaled')
    assert (o.shares.eq(0)&o.fill_time.notna()).any()
    _,a=reconcile_ledger(d,o,b,q,Config())
    assert a['funding_recomputed'] and a['bad_new_risk_admissions']==0
    assert a['bad_quote_price_or_capacity']==0
