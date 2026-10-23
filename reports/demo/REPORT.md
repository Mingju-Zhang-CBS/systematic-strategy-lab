# Fixed-rule allocation experiment

Data kind: **synthetic**. Ticker labels represent simulated roles; these are not actual ETF histories.

|Strategy|Total return|Excess Sharpe|Maximum drawdown|Total trading costs|
|---|---:|---:|---:|---:|
|momentum|13.65%|0.049|-17.61%|701.92|
|static|9.35%|-0.065|-16.94%|63.17|
|spy|14.53%|0.087|-24.72%|29.70|
|qqq|85.03%|0.601|-36.95%|29.70|

![Account performance](performance.png)

![Cost and delay sensitivity](cost_delay.png)

## Economic conventions

The signal compares total-return indices over observations t-252 through t-21. At the first eligible close and subsequent month ends, positive-momentum assets receive equal target weights, capped at 50% each and 99% gross. A trailing 126-observation covariance scales risk down toward a 10% annual volatility budget. These are target limits at decision time; subsequent market moves can change realized weights. Static allocation uses equal weights without volatility scaling. SPY and QQQ controls enter once and then hold.

Weights are frozen at the decision close and executed at a later close. Integer quantities use the NAV and prices observed at execution; sales precede cash-constrained purchases. Costs apply to both purchases and sales. Cash earns the previous observed annual rate over actual elapsed days. Dividends accrue on the ex-date into receivables, become available after 20 supplied sessions, and are not spent or invested before payment. Split multipliers are new shares per old share; dividends are per post-split share. All strategies share the warmup and evaluation dates. Return statistics annualize at 252 observations; gross turnover is traded notional/NAV, not half that value.

## Checks and limitations

Every row reconciles ending NAV to prior NAV, stock price P&L, dividend entitlement, cash interest and fees. Selling and buying are modeled at daily closing prices; the example does not establish available liquidity, fills or capacity. Volume is validated but not used to claim participation limits. Dividend payment dates are an explicit model assumption. Signal thresholds and sensitivity scenarios are fixed; no best row is promoted. Historical user-data results are exploratory when those data have previously been inspected. This synthetic demonstration establishes accounting behavior, not alpha or an independent out-of-sample result.

See `manifest.json`, `metrics.json` and the per-strategy ledgers for configuration, source binding and measured resources.
