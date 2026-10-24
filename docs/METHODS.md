# Real allocation study: information, risk and accounting

## Data and instruments

The offline snapshot has `date,G,F,C,S,I`: five strictly positive accumulation fund NAVs on each supplied official valuation date. It spans 2 June 2003–31 December 2025 and contains 5,639 rows. No market calendar, missing price or return is filled in. These are TSP fund units, not exchange-listed ETFs or benchmark index levels. See [data rights](../DATA_RIGHTS.md) and the [source record](../strategy_lab/data/source.json).

NAV changes include investment income and expenses. `r[f,t] = NAV[f,t]/NAV[f,t−1] − 1` is the observed fund return; separate dividend, cash-rate and expense fields are deliberately rejected. The original synthetic raw-price schema is different and is documented below. Current-vintage data cannot reconstruct exact historical revisions. The I Fund's actual changing mandate is preserved; no constant-index assumption is made.

## Fixed signal and shared risk procedure

For F/C/S/I, momentum is `NAV[t−21]/NAV[t−252] − 1`. Momentum selects positive values; static selects all four. Both assign equal risky allocations subject to a 50% individual target and 99% risky gross target. Using the trailing 126 fund-return rows through t, covariance is estimated with sample degrees of freedom 1 and annualized by 252. If estimated risky volatility exceeds 10%, all risky weights are scaled down proportionally; there is no leverage. The covariance uses risky total returns, so its volatility budget is approximate rather than an exact excess-return budget including the G sleeve.

Each risky target is floored to a whole percentage point; the remainder goes to G. The control shares this algorithm and risk budget, but realized volatility is not forced to equal the momentum portfolio. Comparisons with C buy-and-hold are contextual because exposures differ. Target limits do not continuously constrain weights after market drift.

The first eligible observation is 1 July 2004. Later observations are the previous month's final supplied valuation date, recognized after the next supplied session. No next-session price is used. Default initial capital is $100,000, entirely in G at the previous supplied NAV. Each mode shares the evaluation start and information/posting conventions; C and G controls transfer once, then hold. Boundary windows do not reset or liquidate holdings.

## Four separate clocks

1. **Observation:** last valuation date used in momentum and covariance.
2. **Assumed availability / freeze:** end of one complete subsequent supplied session, recorded at 23:59:59 New York time as a conservative model convention.
3. **Request:** 11:00 New York time on observation+2 supplied sessions by default, strictly after assumed availability.
4. **Posting:** that request day's closing fund NAV, unknown at request time. Ordinary processing is modeled; no guarantee or intraday quote is claimed.

Two-, three- and five-session posting delays are fixed stress cases. A decision with no remaining posting session is not filled at a fabricated final price. Tests mutate future prices and the eventual posting NAV. Exact historical publication times, delayed processing and corrections are not available; the assumed clock is not an archived point-in-time guarantee.

The public [5 CFR Chapter VI rules](https://www.govinfo.gov/content/pkg/CFR-2024-title5-vol3/pdf/CFR-2024-title5-vol3-chapVI.pdf), §§1601.22 and 1601.32, describe whole-percentage reallocations, ordinary noon cutoff/posting and two unrestricted monthly transfers. Each modeled posting month is audited against a maximum of two. Applying that conservative count also before the 2008 restriction does not imply historically exact plan operations. Participant unit rounding, administrative exceptions, eligibility, taxes and external cash flows are omitted.

## Self-financing units and costs

Let `x[f]` be old units, `P[f]` the posting NAV, `w[f]` frozen target weights and `V = ΣxP` pre-transfer value. Solve the scalar equation:

```text
V_after + c × Σ|w[f] × V_after − x[f] × P[f]| = V
x_new[f] = w[f] × V_after / P[f]
```

The fee is funded from the portfolio and both sides of a fund-to-fund transfer count. No-op transfers cost zero. Base `c=0.0003`; stress values are 0, 3 and 10 bp on gross traded notional. These hypothetical costs are neither measured spreads nor additional TSP fund-expense estimates. All strategies in a given comparison pay the same convention. The G sleeve accrues only its observed return.

Each row reconciles `NAV_t = NAV_(t−1) + Σunits_(t−1) × ΔNAV_price − fee_t`. Holdings are fractional, nonnegative fund units. There is no external cash, extra dividend or additional interest. Target-percent execution resembles fund reallocation, not a trader choosing final share quantities after observing an exchange close. Within the model, percentages are known before the posting NAV, while the unit calculation is mechanical afterward.

## Validation, metrics and uncertainty

The [pre-result protocol](../strategy_lab/data/protocol.json) fixes development (July 2004–2014), validation (2015–2019) and confirmation (2020–2025). No validation winner is selected because there is only one prespecified signal rule and its controls. Trailing covariance updates throughout, without refitting on future rows. The report also publishes each calendar year's slice from continuous holdings, with 2004 labeled partial.

Total return compounds daily funded returns. Annualized return and volatility use 252 supplied observations; the former is not an exact elapsed-calendar-time CAGR. Sharpe uses daily portfolio return minus the same-day G return, then annualizes by √252. G's own excess Sharpe is undefined. Maximum drawdown includes starting capital. Gross turnover is total absolute traded notional / pre-transfer NAV, not half turnover. Fee dollars reflect a continuous $100,000 starting account, so window fees are not separately reset normalized accounts.

The primary statistic is `252 × mean(log(1+r_momentum) − log(1+r_static))`, not a CAGR spread or factor-model alpha. Paired non-circular overlapping blocks of 20 and 63 sessions, 2,000 resamples each and seed 20261023 produce percentile 95% intervals. Both are retained. This descriptive exercise assumes approximate local stationarity and does not adjust for all historical strategy discovery. Familiar historical markets, an October 2026 snapshot and missing release vintages prevent a prospective OOS claim. No positive Sharpe or significance threshold is required for publication.

## Separate synthetic accounting reference

The remaining section describes the preserved legacy raw-price demonstration. It is not the real-data input contract or the risk-budget static control above.


<details>
<summary>Legacy synthetic engine: full original contract</summary>

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

</details>
