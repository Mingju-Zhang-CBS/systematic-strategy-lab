# Walkthrough: decisions, cash and one dividend event

## 1. Separate the research signal from the investable account

A total-return index gives a consistent way to measure economic past returns. The tradable account, however, owns actual shares, cash and receivables. It cannot reinvest an ex-date entitlement before the payment date. Reusing a total-return series as if it were a cash account would skip this distinction.

The momentum rule reads observations t-252 through t-21, applies a positivity filter, assigns capped equal target weights, and scales down estimated risk using a trailing covariance. All those inputs are available at the decision close. The trade is scheduled for a later close.

## 2. A target is not an executed order

Frozen decision weights are applied to observed execution NAV/prices, with integer quantities. The engine sells first, subtracts selling fees, and checks cash needed for purchases including buying fees. If cash is insufficient, requested buys are scaled down. Receivables remain in NAV but are not spendable.

The default next-close convention models a target-notional fill. It does not establish that the final closing price was known in advance or that a broker could fill all orders at it. This distinction belongs beside the result, not only in a footnote.

## 3. Trace a split and dividend without changing wealth

The runnable example creates a deterministic market with zero interest and trading fees. A passive account starts with 100,000 currency units and buys 990 shares at 100, leaving 1,000 in cash. On the event date a 2-for-1 split coincides with a dividend of 1 per post-split share; the raw ex-dividend price is 49.

| State | Shares | Raw close | Cash | Receivable | NAV |
| --- | ---: | ---: | ---: | ---: | ---: |
| Before event | 990 | 100 | 1,000 | 0 | 100,000 |
| Split and ex-date | 1,980 | 49 | 1,000 | 1,980 | 100,000 |
| Three supplied sessions later | 1,980 | 49 | 2,980 | 0 | 100,000 |

The split changes units. The ex-date price loss is offset by an entitlement. Payment moves value from receivable to cash; it does not create a second dividend profit. The example uses a three-session lag to make the trace compact; the main study uses 20 sessions.

```text
Before:    990 * 100 + 1,000                  = 100,000
Ex-date: 1,980 * 49 + 1,000 + 1,980           = 100,000
Payment: 1,980 * 49 + 2,980                   = 100,000
```

Run and inspect the event rows:

```text
python examples/explain_accounting.py
```

## 4. Prove the daily bridge before calculating Sharpe

At each supplied session, the engine accrues prior cash at the previous observed annual cash rate over actual elapsed days. It applies splits to existing shares, marks price P&L, accrues dividends, releases due receivables, and executes eligible orders. It then checks:

```text
NAV change = stock price P&L + dividend entitlement + cash interest - fees
```

The main study records 1,260 rows per strategy and 5,040 strategy-day rows in total. Inspect a row in [the momentum ledger](../reports/demo/momentum/ledger.csv), then locate the corresponding [decision](../reports/demo/momentum/decisions.csv) and [order](../reports/demo/momentum/orders.csv). A curve without that connection would be harder to audit.

## 5. Keep the comparison fair and its interpretation qualified

Momentum and static strategies rebalance on the same decision schedule. Passive SPY/QQQ controls enter once, leaving later paid dividends in cash. All use the same warmup, period and financing conventions. They still have different asset and risk exposures; their ranking is not a controlled estimate of signal skill.

The sensitivity grid fixes 0/3/10 bps costs and one/two-session delays. It reports all six cases. There is no mechanism that promotes the best row into a new strategy after inspecting the grid.

## 6. Know what remains outside the model

Volume is validated but does not establish fill capacity. The supplied common sessions are the calendar. Borrow, shorting, margin, impact and taxes are absent. Target risk caps can drift between decisions. Synthetic performance and previously exposed real history cannot be relabeled as pristine future performance.

These are explicit modeling boundaries. The demonstrated skills are temporal accounting, portfolio construction, controlled experiments and testable research software. See [METHODS](METHODS.md), [the report](../reports/demo/REPORT.md) and [the tests](../tests/test_accounting.py).
