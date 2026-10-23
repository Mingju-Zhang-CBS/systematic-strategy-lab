# Account, signal and data contract

## Market inputs

One row per session and ticker; exactly SPY, IEF, GLD, DBC and QQQ on every supplied session. Columns: `date,ticker,close,dividend,split,volume,cash_rate`. Dates are unique timezone-naive midnight session dates, sorted internally. Fields must be finite. Close and split must be positive; dividends and volume nonnegative. Cash rate is a continuously compounded annual decimal, identical across tickers on each session and bounded by an absolute value of 1 as an input-unit check.

Use unadjusted closes. `split` is new shares per old share, normally 1. `dividend` is the ex-date entitlement **per post-split share**, normally zero. Do not combine adjusted closes with separate dividend/split adjustments. Total-return-index growth is `split[t] * (close[t]+dividend[t]) / close[t-1]`. A CSV with undetectable price/volume unit mistakes can still pass schema checks; inspect the source conventions.

No trading calendar is downloaded. Lags count supplied common sessions; unexpected gaps must be reviewed by the data owner. Volume is included for input completeness, not as proof of liquidity or fillability.

## Decisions

`backtest(frame, Config(), mode)` returns daily ledger, decisions and filled-order tables. `mode` is momentum, static, spy or qqq. Momentum uses a 252-observation lookback with the latest 21 observations skipped. Eligible active assets have positive past total returns. Equal target weights are capped at .50 per asset and .99 gross. The trailing 126-observation covariance annualized by 252 reduces target risk if it exceeds .10. A positive signal is not guaranteed to predict positive future performance.

The initial eligible close and subsequent month ends create decisions. Static uses the same calendar and .99/4 target weights without volatility targeting. Passive controls enter once with .99 target weight and do not rebalance or reinvest paid dividends. Target caps apply on decision dates, not continuously after price changes. The synthetic study contains no training/tuning stage; all parameters are fixed demonstration choices.

## Execution and account flow

Each decision freezes weights, to be executed at a close at least one supplied session later. Quantities are integer shares sized from currently observed execution NAV and prices. This is a next-close target-notional execution model; it is not an assertion that a trader can observe the final close and fill arbitrarily at it. Sales occur before purchases. Purchases are proportionally reduced to the available cash after including fees; shorting and borrowing are forbidden. Receivables are not available cash. Both trade sides pay proportional fees; the default is 3 bps of notional.

At each session, prior cash earns the previously observed annual rate over actual elapsed days. Splits change stock quantity. Ex-date dividends create receivables; the default releases them after 20 supplied sessions. There is no interest on receivables. Payment transfers receivable to cash without creating NAV profit. This lag is an explicit assumption, not historical payment-date data.

Every daily row satisfies:

`ending NAV = prior NAV + stock price P&L + dividend entitlement + cash interest - trading fees`.

Ending NAV is cash + receivables + marked stock holdings. The first reported return starts with initial capital; that initial value is also included in maximum drawdown. Gross turnover is total absolute traded notional divided by prior NAV, not half of it. Excess Sharpe uses daily account returns minus the same session cash return and annualizes by sqrt(252). It is descriptive; no statistical significance or realized trading claim is attached.

## Synthetic generator and references

The default generator produces 1,512 business dates, correlated stochastic price movements, stylized regime-dependent drifts, quarterly entitlements and a split. It does not reproduce actual ETF histories, holidays, index survivorship or historical liquidity.

The study uses the familiar momentum building block but does not claim to replicate a published investment strategy exactly. Background: [Kenneth French momentum construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html). All account logic and input conventions are specified here so results can be independently checked.
