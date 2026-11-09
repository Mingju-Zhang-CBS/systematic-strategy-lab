# Does a Cash Gate Improve ETF Momentum?

This independent extension of a graduate systematic-investing assignment holds the ETF pairs and formation rule fixed. It asks what the absolute-momentum cash gate adds to relative momentum once all four accounts trade at the next session close and pay the same fees.

## Findings

The cash gate reduced annualized volatility and month-end drawdown. It gave up compound growth and excess Sharpe to the relative-only and trailing-exposure controls at each of the four cost levels. The dual strategy's worst daily drawdown matched relative-only and was deeper than that of the trailing-exposure control. The lower month-end drawdown therefore missed a material intramonth loss. The trailing control was close to dual in average cash exposure and had less turnover.

Within the same gate, choosing the stronger ETF compounded faster than splitting the sleeve equally. The paired interval at the primary cost included zero, so this sample leaves the size and sign of that ranking benefit uncertain. The two paired log-growth intervals against relative-only and trailing exposure were below zero at the primary cost. These are conditional historical comparisons for one fixed universe and window.

## REM distribution audit

The archived March 2020 adjusted-close return and the CRSP CIZ daily compound differ. Their unadjusted close-to-close moves agree to quote precision. The issuer records a March 25 ex-date and a USD 0.826951 distribution. CRSP's ex-date close reinvestment and the archive's prior-close adjustment each reproduce their respective monthly measures to rounding precision. With a single distribution and no split, the multipliers applied to the monthly price gross return are `1 + D/P_ex` and `P_prev/(P_prev - D)`, respectively. A one-event convention substitution left every executed target unchanged and preserved the four-way ranking. [Issuer distribution record](https://www.ishares.com/us/literature/tax-information/2020-ishares-distribution-summary.pdf) · [WRDS CIZ compounding](https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/wrds-macro-compound-ciz/)

## Research design

| Sleeve | Members |
|---|---|
| Equity | SPY, EFA |
| Credit | HYG, LQD |
| Real estate | VNQ, REM |
| Diversifiers | GLD, TLT |

Each sleeve gets 25% of the account. Signals compound the 12 completed calendar months through the current month-end. The first listed ticker wins a tie. The gate opens only when the winner beats compounded cash over the same period.

| Arm | Exposure rule |
|---|---|
| Relative only | Put the entire sleeve in its winner. |
| Relative with trailing exposure | Put the share of the prior 36 gate decisions that were open in the current winner. Hold the rest in cash. |
| Dual momentum | Put the entire sleeve in its winner when the gate opens. Otherwise hold cash. |
| Same gate, equal pair | Apply the dual gate to the same sleeve and date. Split open sleeves equally between both ETFs. |

Evaluation runs from January 2012 through June 2026. Signal history begins in June 2007. The four arms start in cash, form targets after month-end and rebalance at the first subsequent CRSP trading session's traded close. Old positions earn the return through that close. New positions begin earning ETF returns on the following session. Cash uses the archived French monthly RF series, compounded evenly across each month's sessions for marking. The archival signal assumes the just-completed RF is available at formation. No historical RF publication timestamps were verified.

ETF marks use CRSP CIZ total returns, including the vendor's reinvestment convention. Historical security IDs, the CIZ trading calendar, predecessor dates and traded execution quotes are checked before running. Daily compounds are reconciled to the CRSP monthly file. The runner stops on missing daily ETF returns, invalid execution quotes or delisting flags. Fees are funded from NAV and charged on gross ETF buys plus sells at 0, 5, 10 and 20 bps one-way. The primary cost is 10 bps. The last evaluation session is marked without a forced liquidation. Close fills are modeled at the observed trade price with a fee allowance. The model does not resolve market impact or dividend pay-date liquidity.

The report separates CAGR, monthly excess Sharpe, daily and monthly drawdown, average daily cash, turnover and fees. It uses 3,000 paired 12-month moving-block resamples for annualized mean log-return gaps. The same block positions are used within each pair. Intervals are descriptive and unadjusted for the three comparisons. The ETF universe and evaluation window come from coursework and follow-up analysis, so the results are historical and cannot establish an out-of-sample edge. The trailing gate approximates average exposure and allows date-by-date risk to differ.

## Reproduce

Run the study from the repository root in an authorized WRDS environment with the Python `wrds` client, pandas and NumPy. Set the output directory to a private location. The RF input is a private CSV with columns `month` (YYYY-MM) and `RF` (decimal) covering June 2007 through June 2026. Use the assignment's archived RF column for an exact comparison. An optional private JSON provides the archived REM March price return, total return, ex-date and cash distribution as `price_return`, `total_return`, `ex_date` and `distribution`.

```bash
python -m tools.run_dual_momentum_wrds --rf local-runs/rf.csv --out local-runs/dual-momentum --rem-reference local-runs/rem_reference.json
python -m pytest tests/test_dual_momentum.py
```

The completed run is `dual-momentum-crsp-v1-20261109`. It writes a versioned summary with fingerprints, 16 daily ledgers, net monthly and calendar-year returns at 10 bps, and paired intervals. Full numerical results and the one-event perturbation are retained privately with the research run. The repository publishes original methods, code, tests and narrative research findings. [Data rights](../../DATA_RIGHTS.md) · [French factor data](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)

Wharton Research Data Services (WRDS) was used in preparing *Does a Cash Gate Improve ETF Momentum?* This service and the data available thereon constitute valuable intellectual property and trade secrets of WRDS and/or its third-party suppliers. Data source: CRSP US Stock Database, CIZ, 2026, Center for Research in Security Prices, LLC.
