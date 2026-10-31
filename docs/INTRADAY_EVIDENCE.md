# Resolving an Observation Is Different from Improving a Strategy

**Question:** does the source establish what was available before a decision?

[Worked example](../reports/intraday-evidence-fixture/REPORT.md) · [Implementation](../strategy_lab/intraday/evidence.py) · [Tests](../tests/test_intraday_evidence.py) · [Original source audit](INTRADAY_SOURCE_AUDIT.md)

![Invented clock cases](../reports/intraday-evidence-fixture/evidence_clocks.png)

## Recover precision before comparing clocks

A SIP record can store a microsecond timestamp and a separate nanosecond remainder.
Comparing only the first field with a derived table can create an apparent clock
disagreement. Recover the full clock as `microsecond timestamp + remainder`;
never add the remainder twice or infer it from a price move.

The cluster check requires exact asset, price and share-quantity correspondence,
explicit dated lot units and a unique match for each coarse tuple. Fine timestamps
must lie strictly inside the coarse label's half-microsecond neighborhood. A tie
at 500 ns is left unresolved. Message sequences are checked inside a single source
scope, not compared indiscriminately across feeds. Distinct fine messages can then
explain a collision under rounding; this does not establish an undocumented vendor
algorithm or authenticate the original feed.

Recovered observations retain their fine time. The existing execution engine must
still check arrival and expiry. A rounded quote at the arrival boundary might
actually have preceded the request. Restoring order does not authorize a new fill
window, extra child orders, more displayed capacity or an account restart.

Unmatched clusters remain in an audit table. Keep the original coarse file, raw
fine messages, conversion evidence and recovery output as separate artifacts.
An old stopped account remains an old stopped account even if a later source
exception is repaired.

## A distribution schedule is not an amount release

Record security identity, **US** ex-date, gross currency/amount per share,
document fingerprint, source, release timestamp/timezone and correction status.
Separate evidence of the calendar from evidence of the amount. Net receipts after
withholding do not replace the gross distribution used for a price adjustment.

For example, the issuer's [September 2025 schedule](https://www.invesco.com/content/dam/invesco/hk/en/pdf/Q3-2025-distribution-announcement-20250910-EN.pdf)
specifies Hong Kong dates and says that a later announcement will provide the
amount. Its [amount document](https://www.invesco.com/content/dam/invesco/hk/en/pdf/third-quarter-distribution-announcement-20250921-EN.pdf)
is dated 21 September and gives USD 0.69395 per share. The title names the third
quarter, while one body sentence names the second; the [issuer's exchange form](https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0921/2025092100033.pdf)
identifies the third-quarter distribution. Preserve the inconsistency rather than
silently editing the source. The [US issuer history](https://www.invesco.com/us/en/financial-products/etfs/invesco-qqq-trust-series-1.html)
lists the US ex-date as 22 September. Those sources support identity, amount and
calendar distinctions; a printed date or a current page alone does not establish
the exact historical publication timestamp.

`evaluate_action_evidence` checks an analyst-verified primary release clock
strictly before the supplied decision. Date-only documents, schedules, unmatched
amounts and releases at or after the decision cannot clear that strict check.
It validates attestations; it cannot independently verify their truth. Save the
source document and release listing, not merely a boolean flag.

The original action adapter's prior-day declaration-date convention remains an
explicit **current-vintage end-of-day proxy**. A matching alternate vendor date
may be evaluated under that same convention in a separately recorded overlay;
it must not be relabeled as a verified primary publication timestamp. Missing
or same-day dates remain unavailable before the open without additional evidence.

## What changes, and what stays fixed

Source adjudication changes a documented observation only when its evidence
passes. Signal definitions, costs, financing, latency, one-snapshot fills and stop
conditions remain frozen. Record adjudication before the corrected replay and
disclose that earlier results have already been seen. No new untouched holdout
is created by correcting historical data.

The licensed replay and its source map remain private. Public examples above are
invented; the issuer case uses linked public facts. No complete ten-year return,
Sharpe, significance result or realizable execution claim follows from the
evidence checks. Development and automated verification were AI-assisted.
