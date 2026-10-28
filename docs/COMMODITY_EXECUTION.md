# Exit first: an execution protocol comparison

An outgoing contract should not remain open merely because its replacement
cannot be opened. This extension tests that engineering claim without relaxing
the outgoing contract's own execution checks or optimizing historical returns.
The original coupled engine and its synthetic report remain available.

## Three frozen protocols

|CLI policy|Orders|Candidate liquidity|Maturity selection|
|---|---|---|---|
|`legacy` (default)|One coupled close/replacement basket per product|One lagged observation|Earliest qualifying pair each day|
|`split_only`|Portfolio reductions, then optional additions|Original one-observation rule|Original rule|
|`persistent`|Portfolio reductions, then optional additions|Five consecutive lagged observations|Nondecreasing near/far maturity floors|

The primary engineering revision is `persistent`. The split-only base experiment
isolates order routing with the original reference histories. The primary also
rebuilds reference histories and signals under a new selection rule: its change
in P&L cannot be attributed entirely to execution. Five observations, the
activity thresholds, roll floors, all costs and the original eleven stress
cases were fixed before the revised experiments. There is no search over
window length, maturity buffer or strategy coefficients using returns.

```text
python -m strategy_lab.commodities.research_report --fixture --policy persistent --output local-runs/exit-first
python -m strategy_lab.commodities.research_report --fixture --policy split_only --base-only --output local-runs/split-only
python -m strategy_lab.commodities.research_report --fixture --policy legacy --output local-runs/legacy
python -m pytest tests/test_commodity_exit_priority.py
```

For licensed inputs, replace `--fixture` with `--input PRIVATE_INPUT` and keep
the entire output private unless its publication is permitted. The
[synthetic execution report](../reports/commodity-exit-priority-synthetic/REPORT.md)
contains invented curves only. The [original packet](../reports/commodity-research-synthetic/REPORT.md)
preserves the previous version and its fingerprints.

## One frozen request, two execution phases

1. Compute signals, risk, integer quantities and targets using permitted t−2
   observations and account equity. Today's execution reference does not resize
   the request.
2. Mark old positions and book their variation margin.
3. Process reductions for **all products** before any additions. If a contract
   set changes or direction reverses, close the entire old product basket.
   Otherwise reduce existing quantities toward the frozen target. A two-leg
   spread close remains atomic; neither leg is deliberately abandoned alone.
4. Attempt new or increased risk only after that product's required reduction
   succeeds. Failure elsewhere does not silently cancel a feasible reduction.
5. Retain every rejection. An unfilled exit at its known delivery boundary still
   stops the funded path; it is never assigned an imaginary liquidation price.

The old and replacement spread may share a contract. This implementation closes
and reopens that overlap rather than netting it. Each side pays its own fees and
slippage and consumes the **same daily contract-side capacity**. This is a
conservative routing convention, not an exchange spread-fill simulation. The
pre-trade fee budget uses net target changes as an estimate; actual phase costs
are fully charged and post-mark funding is checked before each basket executes.

**Example.** Hold one June contract; the next request is one September contract.
June can close under its lagged capacity, but September cannot open. The legacy
basket leaves June open. Exit-first closes June, charges its cost and remains
flat. If June itself cannot close, both policies retain that failure. If an old
spread's second leg lacks a reference, the pair is not falsely closed.

The tape retains `filled_reduce_basket`, `filled_open_basket`,
`unfilled_reduce_basket`, `unfilled_open_basket` and
`entry_blocked_by_unfilled_exit`. Trade order, contract quantities, per-side
costs and daily cash remain separately inspectable. No notional principal is
paid on entry; collateral reserves encumber cash and are not a second expense.

## Persistent admission and monotone rolls

At decision day d, the five scheduled observations ending at d−2 must **each**
have volume ≥100 and open interest ≥100. Missing activity breaks qualification.
It is an admission rule, not a guarantee that the requested quantity can fill:
each phase separately checks cumulative absolute sides against
`floor(1% × volume[d−2])`, a finite EOD reference and positive execution-day
activity. There is no capacity exemption for risk reduction.

Among candidates satisfying the existing listing, unit and known-boundary
rules, choose the earliest two maturities. Once a valid pair is selected, neither
near nor far may subsequently move to an earlier delivery month. Temporary
illiquidity can cause a forward move or no eligible pair; recovery does not
undo that move. An invalid selection does not advance the floors. All decisions
use past activity; future volume cannot improve historical admission.

These rules can exit early, skip maturities, increase costs or leave no signal
history. Those outcomes remain in coverage and failure tables. Missing front
notice/specification evidence retains the documented gate; monotonicity does
not manufacture missing first-position records or original publication dates.
Five/ten scheduled-session boundary buffers remain assumptions under the
authorized calendar proxy, not a certification against physical delivery.

## What the comparison can establish

All five rules, two separately funded benchmark sleeves and eleven original
cost/delay/sector/reserve cases remain fixed. The original funded baseline must
reproduce numerically; the split-only case identifies whether coupling blocked
feasible closes. The persistent case checks the whole revised research path.
Failure counts, coverage, costs and independent cash reconciliation come before
premium inference. Completed paths are not selected because they make money.

The history has already been inspected. Phase labels in the inherited bootstrap
are historical diagnostics, **not new independent out-of-sample confirmation**.
An incomplete or stale required path remains not evaluable, distinct from a
valid test whose interval includes zero. No new result is automatically evidence
of executable alpha. Scheduled calendars, current-vintage metadata, modeled
fills and 10%/20% gross collateral proxies retain their original limitations.

See [research methods](COMMODITY_RESEARCH.md),
[execution invariants](../tests/test_commodity_exit_priority.py),
[accounting tests](../tests/test_commodity_research.py) and
[data rights](../DATA_RIGHTS.md). Research choices were directed by Mingju Zhang;
implementation and experiments were AI-assisted. Independent personal review
and original licensed source evidence remain separately tracked.
