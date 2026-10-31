# Source Evidence Before a Performance Claim

**Question:** which observations were usable before the decision, and can an independent ledger reproduce what followed?

This extension adds a [corporate-action adapter](../strategy_lab/intraday/actions.py), [cash reference](../strategy_lab/intraday/reference.py) and [independent order-ledger reconstruction](../strategy_lab/intraday/reconcile.py). The trading rules, three variants, two delays, costs and funding proxies in the original frozen protocol remain unchanged. The sole engine change accepts mixed whole-second/subsecond CSV timestamps explicitly at the input boundary.

[Invented worked examples](../reports/intraday-data-fixture/REPORT.md) · [Original execution report](../reports/intraday-synthetic/REPORT.md) · [Data status](INTRADAY_DATA_STATUS.md)

[Source protocol summary](INTRADAY_SOURCE_PROTOCOL.json) connects the original freeze to the private source/cash decision fingerprints. This public summary was written after the initial private diagnostic; it is not represented as a new pre-outcome frozen artifact. The original decision records and clock-correction rationale are retained separately.

## 1. Identity and action units

Join each security day to the identity interval effective on that date. Duplicate or unmatched identities fail the join; a later ticker record cannot resolve an earlier date. Daily coverage must be established before interpreting the absence of an event as no action. Ordinary and nonordinary cash distributions must reconcile to the explicit event records; unsupported events remain blockers.

The adapter checks `(current close + cash distribution) × split ratio / previous close − 1` against the supplied daily total return. A synthetic $1 distribution and 2-for-1 split exercise the units independently. Numerical agreement is a consistency check, not proof of original-release availability or universal treatment of reorganizations.

Declaration **dates** and precise publication **timestamps** are different evidence. A prior-day declaration is assigned a conservative end-of-day proxy; a missing or same-day declaration cannot establish that the amount was known before the open. Those records remain unavailable. Current-vintage vendor histories can also incorporate later corrections, so these controls do not establish a complete historical PIT feed.

The frozen strategy normally holds no overnight shares. Actions adjust the prior-close anchor and lagged total returns; adding a cash dividend to an intraday account with no entitlement would double-count income. An unclosed position stops the account; the code does not invent later dividend settlement, borrowing or liquidation.

## 2. Cash opportunity cost

EFFR is a reference rate, not a deposit available to this account. The strategy's original idle-cash credit remains zero. A separate opportunity-cost account compounds the last rate known at each interval start using ACT/360 calendar-day accrual: first open to first close, then close to close, including weekends. This benchmark never changes orders.

The [NY Fed](https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates) describes next-business-day publication at approximately 09:00 ET and possible same-day revisions near 14:30. The primary current-vintage proxy therefore uses **14:45 ET** availability; the earlier **09:15 ET** assumption is retained as a sensitivity. Following effective-observation dates provide an explicit scheduled-calendar proxy; they are not archived actual release times. Exceptional revisions and missing original vintages remain limitations. The last source observation has no inferred following release and is omitted rather than backfilled into earlier decisions. The EFFR methodology changed in March 2016. Calendar-day accrual uses New York wall dates: a daylight-saving weekend remains three calendar days, rather than 71/24 or 73/24 days. This differs from the strategy's explicitly elapsed-second financing approximation.

## 3. Ambiguous quotes and opening evidence

Identical timestamps can contain different prices or displayed quantities. Quarantine conflicting records; do not pick the best price, largest size or an arbitrary row. A later uniquely identified valid quote can be used only inside the original request window. Source ambiguity is distinct from evidence of actual market illiquidity. A complete-NBBO extract lacking message sequence cannot by itself reconstruct feed ordering.

Opening-auction identification also requires the actual event time and listing-venue conventions. An auction outside a narrow extraction interval must be investigated rather than replaced by a bar close. If its time cannot be shown to precede the signal, it cannot supply that signal's opening reference.

The [precision and publication study](INTRADAY_EVIDENCE.md) adds explicit fine-clock cluster matching and a primary publication-evidence check. A microsecond field must be combined with its separate nanosecond remainder before comparing a raw SIP clock with a lower-precision derived table. The extraction helper now searches for the primary opening auction before the first 10:00 signal, rather than assuming it occurred by 09:31; the original extraction and failed replay remain separate retained artifacts.

## 4. Reconstruct the account

The independent audit uses signed order quantities, bid/ask observations, elapsed time and configured charges to recompute cash, financing, short-borrow costs, shares and marked equity. It checks fill latency, side price, displayed capacity and margin on new risk. Valid reductions remain separate from admission decisions.

Quoted attempts with zero admitted shares still advance the financing clock; they are not sell fills merely because their quantity is nonpositive. Missing-quote attempts do not advance that clock. Borrow marks follow the latest observable decision/quote mark under the declared discrete approximation, rather than a continuous borrow valuation.

Closing under the frozen one-snapshot fill policy can leave inventory after a partial fill. Retain it, mark residual equity provisionally and stop. This does not prove an ETF was impossible to liquidate in the market: repeated child orders, other routes and post-close execution are outside this protocol. Extending execution after observing a failure requires a new protocol and a preserved baseline.

## 5. What may be concluded

A private replay of a fully labeled initial data prefix is an accounting diagnostic, not the complete 2016–2025 study. Do not silently restart stopped accounts, stitch them into NAV, set remaining inventory to zero or assign zero returns to unvisited validation/confirmation dates. Unknown action clocks block continuation. Positive and negative partial marks are retained without ranking them as comparable completed strategies.

Full-window Sharpe, block intervals and significance results are **not estimated** for an incomplete/stopped target path. “Not estimated” is not a nonsignificant statistical finding. The intended periods and all fixed variants remain in the status report, including those that cannot be evaluated.

Licensed raw observations and source-derived private reports remain outside this repository. Public additions are original methods, tests and invented known-answer examples. [CRSP distribution definitions](https://www.crsp.org/wp-content/uploads/DistributionCode.html) and [data description](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-data-descriptions-guide-crspaccess/) guide field interpretation; their license is not replaced by the code's MIT license. Development and automated verification were AI-assisted; no independent human-mastery claim follows.
