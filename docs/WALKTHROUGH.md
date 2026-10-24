# Walkthrough: from an observation to a funded allocation

## 1. Interpret the data before calculating a signal

The [CSV](../strategy_lab/data/tsp_nav.csv) contains five actual fund share NAVs. C/S/I are equity exposures, F is a bond fund and G is a special government-securities reserve. A move from 100 to 102 already reflects the fund's income and expenses; it is a 2% fund return, not a 2% price return plus an estimated dividend. Public access to fund facts does not make these restricted retirement units universally investable.

## 2. Separate valuation, knowledge and execution

Take an illustrative month-end observation on a Friday. Momentum and covariance use Friday and earlier values. Monday is a complete intervening supplied session reserved for publication; freeze the targets after it. Request the allocation at 11:00 New York time Tuesday and model posting at Tuesday's closing NAV. Monday or Tuesday prices do not enter Friday's signal. If a holiday removes a supplied valuation session, the model counts supplied sessions rather than pretending every weekday was tradable. The actual [decision CSV](../reports/real/momentum/decisions.csv) records each date and clock.

This is a conservative assumed clock, not reconstructed publication evidence. A correction to a past NAV could still contaminate a current-vintage history; sensitivity to extra delay cannot prove that this risk is absent.

## 3. Transform a signal into a funded target

For an illustrative four eligible funds, equal risky weights start at 24.75% each. If the trailing estimated volatility exceeds 10%, scale them down, then floor each to a whole percentage and assign the remainder to G. All-negative momentum gives 100% G. The static control always selects all four but shares this risk and rounding procedure. Thus the control asks whether filtering eligibility helps beyond the allocation machinery; it does not promise identical realized risk.

## 4. Follow one fee through both transfer legs

Run `python examples/explain_nav_transfer.py`. Begin with 1,000 G units at NAV 100 ($100,000). Request 100% C. At an illustrative posting C NAV of 100, with 10 bp hypothetical friction on every gross dollar sold or bought:

```text
Sell G value                                  100,000.000000
Buy C value = 100,000 × (1−0.001)/(1+0.001)     99,800.199800
Gross traded value                            199,800.199800
Fee = gross × 0.001                               199.800200
After-fee C units                                 998.001998
```

Purchased value plus fee equals the initial value. If C NAV rises to 102, the position is worth $101,796.203796. The observed $1,996.003996 increase is the entire NAV return for the position; a separate dividend credit would double-count it. No external cash funds the fee. The base study uses 3 bp, while this 10 bp example makes both transfer legs easier to see.

## 5. Read a daily bridge and a comparison

In the [ledger](../reports/real/momentum/ledger.csv), `prior_nav + price_income_pnl − fee` equals `nav`. Unit columns reconstruct ending value using the source NAV. The order table shows the frozen target, actual posting NAV, changed units and modeled fee. Realized weights drift between postings.

The confirmation comparison is not a high-Sharpe sales pitch. Momentum returned 30.69% versus 33.97% for the shared-risk-budget static control; the paired annualized log-return difference was −0.42 percentage points and both block intervals contain zero. Read the [complete report](../reports/real/REPORT.md) for all periods, all nine cost/delay combinations and annual failures. Chronological historical checks are useful, but they are not unseen future evidence.

## 6. Keep the two educational contracts distinct

The [legacy split/dividend example](../examples/explain_accounting.py) uses synthetic unadjusted prices, an ex-date receivable and a delayed cash payment. That mechanism is appropriate for its explicit raw-price contract. The real accumulation-NAV study has no separate payment-date ledger. Both teach conservation, but combining them would count income twice.
