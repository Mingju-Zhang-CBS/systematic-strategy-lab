# Does a Cash Gate Improve ETF Momentum?

This independent extension of a graduate systematic-investing assignment holds the ETF pairs and formation rule fixed. It asks what the absolute-momentum cash gate adds to relative momentum once all four accounts trade at the next session close and pay the same fees.

## Findings

The cash gate reduced annualized volatility and month-end drawdown. It gave up compound growth and excess Sharpe to the relative-only and trailing-exposure controls at each of the four cost levels. The dual strategy's worst daily drawdown matched relative-only and was deeper than that of the trailing-exposure control. The lower month-end drawdown therefore missed a material intramonth loss. The trailing control was close to dual in average cash exposure and had less turnover.

Within the same gate, choosing the stronger ETF compounded faster than splitting the sleeve equally. The paired interval at the primary cost included zero, so this sample leaves the size and sign of that ranking benefit uncertain. The two paired log-growth intervals against relative-only and trailing exposure were below zero at the primary cost. These are conditional historical comparisons for one fixed universe and window.

## What drove the gap

Cash spells explain most of the underperformance against the two relative-momentum controls. The largest calendar-period losses were in 2020, 2023 and 2016. Equity and real estate exits missed rebounds after the March 2020 decline. In 2022, cash helped, particularly in real estate and credit. Real estate was the largest full-window detractor against both relative controls. Equity and gold/Treasuries also detracted, while credit was close to flat against relative-only.

Both relative controls select the same winner as dual whenever they hold a risky position. Their gap is attributable to exposure and fees. Against the same-gate equal pair, selection helped on average, led by gold/Treasuries, with sizeable losing intervals as well. In March 2020 the real estate sleeve's choice of VNQ helped against the equal pair through the execution close. The subsequent VNQ exit missed the recovery captured by relative-only. Higher turnover widened the return gap. Winner rotations accounted for the largest share of dual's own trading cost, and cash exits and re-entries added turnover. Both relative controls also rotated, limiting the relative fee drag.

The attribution replays the frozen accounts and checks daily NAV, net returns and turnover. Within each sleeve it separates differences in risky weight, ETF mix and fees. On days only one account is invested, its mix anchors the comparison, assigning the gap to exposure. Each day's components are linked to the difference in net log returns, so they add across sleeves and calendar periods. The private report retains the full year-by-sleeve matrices, both favorable and unfavorable trades, and the detailed fees. These effects describe the historical paths under the recorded execution rule.

```bash
python -m tools.run_dual_momentum_attribution --rf local-runs/rf.csv --base-dir local-runs/dual-momentum
python -m pytest tests/test_dual_momentum_attribution.py
```


## Rebound follow-up

Two fixed variants respond to the missed rallies on the same historical window. The half-risk floor keeps half of each closed sleeve in its 12-month winner. The three-month rule keeps the initial cash exit. On later monthly decisions while the long gate is still shut, the same 12-month winner can re-enter if its three-month return beats cash over the same period. Both variants keep the original signal clock, next-session close, cost grid and asset universe. The four original strategies reconcile across all four costs.

The half-risk floor recovered about half of the original missed exposure P&L and retained about half of the protection on the original cash spells. It improved growth and excess Sharpe versus original dual across the cost grid. It still trailed pure relative momentum and the trailing-exposure control on both measures. The faster rule restored risk in relatively few of the original missed spells, entered during several of the protective spells and increased turnover. Its improvement over original dual was small and the paired interval included zero. Neither variant improved the original worst daily drawdown, which occurred before the April 2020 cash exits.

The private report compares all six arms and costs, retains both positive and negative cash spells and reports the 2020 equity and real estate cases, the protective real-estate spell that began in 2022, and the full calendar-year panel. The missed and protective groups use the sign of each original spell's realized exposure effect. The comparison sums variant exposure contributions over those same windows and evaluates fees separately in the portfolio accounts. The two rules were specified after observing the original attribution and before running the variants. The historical evaluation therefore measures the trade-off in this sample.

```bash
python -m tools.run_dual_momentum_rebound --rf local-runs/rf.csv --base-dir local-runs/dual-momentum
python -m pytest tests/test_dual_momentum_rebound.py
```


## Rolling cash-floor validation

Three fixed candidates retain 25%, 50% or 75% of a closed sleeve in its same 12-month winner. They use annual historical holdouts beginning in 2017 and ending in June 2026. The fixed accounts and original controls carry holdings across all year boundaries. A separate selector ranks the fixed candidates by net excess Sharpe over the prior 60 completed months at the primary cost, chooses once per year and trades one continuous account. Its decisions are frozen across the four cost levels. The original accounts and earlier half-risk result were reconciled before evaluating the holdout.

The half-risk floor consistently recovered about half of the original missed cash-spell exposure and retained about half of the protection where those effects were present. That stability is consistent with scaling the same ETF exposure. Half risk improved growth over original dual and fell short of the trailing-exposure control in the pooled holdout at every cost. It won half the calendar folds against that control and the paired interval included zero. Its month-end drawdown was shallower than the control's, while its daily drawdown was deeper.

The 25% floor retained the most protection and grew the slowest among the candidates. The 75% floor had the strongest growth among the floors and exceeded trailing exposure in pooled net growth at every cost. It gave up most of the original cash-spell protection, with a deeper daily drawdown than trailing exposure and a paired interval that included zero. The rolling selector matched the fixed 75% result. Its switch to 50% occurred in a holdout period when no closed-gate returns were observed.

The private report keeps all calendar folds, training scores, all four costs, paired intervals and cash-fragment denominators. For each fold the original cash spells are split at its boundaries, labeled by their realized original effect, and compared against the same days under the new floors. The original attribution informed the test, so the results describe historical holdouts on a reused sample.

```bash
python -m tools.run_dual_momentum_walkforward --rf local-runs/rf.csv --base-dir local-runs/dual-momentum
python -m pytest tests/test_dual_momentum_walkforward.py
```


## Volatility-matched test of the 75% floor

At each annual fold, the two strategies are matched to the lower of their unscaled prior 60-month volatilities. Risk is the annualized volatility of net monthly excess returns over cash from a funded replay at the primary cost. The higher-risk portfolio scales all of its ETF targets down and leaves the residual in cash. The scale is frozen for the next test fold and used at all four costs. The accounts keep the original next-session close, cash proxy and trade fees, including resizing. They carry positions across folds.

The 75% rule kept a small pooled growth lead after matching, but the lead narrowed at every cost. The paired intervals included zero, excess Sharpe was essentially the same at the primary fee, and the matched floor still realized higher pooled volatility. Trailing exposure had the lower training risk in every fold and kept its original weights.

Scaling reduced the 75% portfolio's 2022 loss and daily drawdown. Trailing exposure still lost less and drew down less over the full calendar year. The scaled 75% account retained slightly more of original dual's protection on the original protective cash fragments than it did before resizing. The full calendar outcome and cash-fragment result measure different portions of the portfolio path. The report evaluates time-ordered historical holdouts on the same research sample.

```bash
python -m tools.run_dual_momentum_volmatch --rf local-runs/rf.csv --base-dir local-runs/dual-momentum
python -m pytest tests/test_dual_momentum_volmatch.py
```


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
