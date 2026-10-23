"""Follow one synthetic split, ex-date entitlement and payment through NAV."""
import numpy as np
from strategy_lab.core import synthetic_market,Config,backtest

def main():
    market=synthetic_market(30)
    market['close']=100.;market['dividend']=0.;market['split']=1.;market['cash_rate']=0.
    dates=sorted(market.date.unique());event=dates[15]
    market.loc[(market.ticker=='SPY')&(market.date>=event),'close']=49.
    market.loc[(market.ticker=='SPY')&(market.date==event),['split','dividend']]=[2.,1.]
    config=Config(lookback=10,skip=2,covariance_window=5,cost_bps=0.,dividend_payment_lag=3)
    ledger,_,_=backtest(market,config,mode='spy')
    trace=ledger[ledger.date.isin([dates[14],dates[15],dates[18]])]
    np.testing.assert_allclose(trace.nav,100_000.,atol=1e-8)
    assert trace.receivable.iloc[1]==1980 and trace.receivable.iloc[2]==0
    print('Synthetic split/dividend trace; zero costs and interest:')
    print(trace[['date','shares_SPY','cash','receivable','dividend_accrual','dividend_payment','nav','bridge_error']].to_string(index=False))
    print('Payment transfers receivable to cash without creating new NAV profit.')

if __name__=='__main__':main()
