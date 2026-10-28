# Retiring a futures position without inventing liquidity

Capacity-limited retirement is a different question from a profitable signal.
This revision first diagnoses the old basket, then freezes a paired reduction
schedule and an earlier retirement trigger. It retains all previous protocols,
uses the same eight-market research inputs and does not search over returns.
Public results are **invented demonstrations**. Licensed snapshots and their
derived findings remain private.

## Protocols and reproduction

|Policy|Reduction request|Earlier retirement|Selection and signals|
|---|---|---|---|
|`persistent`|Whole old basket or rejection|Original known-boundary roll|Previous five-observation admission and monotone maturities|
|`partial_only`|Capacity-sized paired slices with a latched goal|None|Same as `persistent`|
|`capacity_exit`|Capacity-sized paired slices with a latched goal|Fixed lead or estimated drain-time pressure|Same reference histories and signal definitions|

```text
python -m strategy_lab.commodities.research_report --fixture --policy capacity_exit --output local-runs/staged
python -m strategy_lab.commodities.research_report --fixture --policy partial_only --base-only --output local-runs/partial
python -m strategy_lab.commodities.research_report --fixture --policy persistent --output local-runs/retained
python -m pytest tests/test_commodity_staged_exit.py
python examples/explain_staged_exit.py --output local-runs/paired-trace
```

The primary experiment retains all eleven predefined cost, delay, collateral,
boundary and sector scenarios, with five strategies and two separately funded
benchmark sleeves each. The partial-only base diagnostic isolates slicing from
the early trigger. The complete prior persistent experiment must reproduce.
The [new synthetic report](../reports/commodity-staged-exit-synthetic/REPORT.md),
[previous exit-first report](../reports/commodity-exit-priority-synthetic/REPORT.md)
and [original coupled report](../reports/commodity-research-synthetic/REPORT.md)
have separate code/configuration/output fingerprints. The default remains
`legacy` for compatibility. For licensed input, substitute `--input PRIVATE_INPUT`
and keep its output private unless publication rights are established.

The [controlled paired-exit trace](../reports/commodity-staged-exit-synthetic/controlled-retirement/REPORT.md)
separately makes the weaker leg bind: +2/−2 reduces to +1/−1 and then flat.
Its activity is deliberately constructed relative to initial size; it explains
accounting and ordering rather than calibrating a trading strategy.

## Start with the whole old basket

A stopped front contract is not necessarily the bottleneck. Reconstruct actual
positions from fills, inspect **every old leg**, and compare quantity with its
own lagged capacity and current execution reference/activity. A near leg might
have capacity 50 while the old far leg has capacity one. Those are both existing
positions, distinct from a rejected replacement order. Historical capacity
windows diagnose what happened; they do not estimate exchange fill probabilities.

The ledger still marks old contracts before trading. A reduction is frozen
before the execution reference, using information through d−2 at a 07:00 Chicago
decision. Today's price or volume can reject the frozen slice; it cannot enlarge
it, determine a more convenient position size, or repair a missing old mark.

## One paired unit, one binding capacity

For each changed old leg k, define the integer contract-side allowance

`capacity[k,d] = floor(0.01 × volume[k,d−2])`.

The unit allowance is the minimum across the old legs being reduced. A spread
with near +6 and far −6, capacities four and two, can reduce **two paired units**:
sell two near, buy two far, retain +4/−4. A zero allowance means zero units.
Missing either execution reference or positive activity rejects the entire
planned slice. The model never deliberately strands one leg.

All portfolio reductions precede additions. Both phases consume the same
absolute contract-side allowance, and overlapping old/new spread contracts pay
both closing and opening costs. No capacity is reused after the last old slice.
Cash, fees and collateral are checked for each actual modeled basket. Paired
EOD slices are an explicit execution assumption, not evidence of an exchange
spread fill or synchronized bid/ask liquidity.

## Preserve the exit goal across days

A roll or sign reversal latches the old product's goal at zero. A same-contract
risk reduction latches its smaller quantity. While pending, the goal can shrink
but cannot grow; a changed signal cannot cancel unfinished retirement. New or
increased risk in that product remains blocked until actual modeled fills reach
the goal. Other products' feasible reductions proceed independently.

Each session writes `exit_plans.csv.gz`: observation date, old contracts, held
units, goal units, required/planned reduction, permitted current slice capacity,
conservative capacity, sessions to the hard boundary and retired near maturity.
Trades, rejections, holdings and variation-margin records distinguish a planned
slice from a successful one. No partial progress is assumed after a rejection.

## Earlier retirement: an explicit assumption

For a held outright or paired unit, take the earliest old-leg hard deadline.
The deadline remains the known FND/LTD boundary minus the original five scheduled
sessions, or ten in its predefined stress. Let

- `remaining = deadline_index − decision_index + 1`, including today;
- `conservative_capacity` be the minimum integer allowance across all old legs
  and five scheduled observations ending at d−2; missing activity gives zero;
- `drain_days = ceil(held_units / conservative_capacity)` when positive.

Start full retirement if **remaining ≤10**, **remaining ≤drain_days +2**, or
conservative capacity is zero. Ten lead sessions, five capacity observations,
two spare sessions and 1% participation are fixed research assumptions, not
calibrated market estimates. The projected drain rate can deteriorate. Actual
daily slices still use only that day's permitted lagged allowance.

Early retirement locks out the outgoing near maturity: it cannot be reopened at
the same or an earlier near month. Resume only after selection advances and the
old basket is flat. The trigger day suppresses replacement entry; an ordinary
non-early roll can open its replacement on the completion day if capacity and
funding permit. The early trigger applies to **held inventory**; it is not an
additional candidate-entry calendar filter. A newly entered unit can therefore
retire on the following decision. This conservative turnover cost is retained.

No return, drawdown or favorable realized spread enters this trigger. Signal
rankings and same-contract reference histories are unchanged. Retiring inventory,
time spent flat, costs and evolving account equity can change later funded risk
allocations, so terminal changes are not a pure isolated trading-cost estimate.

## Failure remains an admissible outcome

An unfinished old unit at its original hard deadline still stops the funded
path. Zero capacity, a missing leg, funding failure and nonpositive equity are
not exceptions to bypass. There is no synthetic liquidation, replenishment,
cross-leg reserve credit or replacement of failed primary accounts by surviving
small-capital or sector cases. Failed/stale/incomplete primary comparisons stay
not evaluable; an evaluable interval spanning zero is a different result.

All historical evaluation windows have already been inspected. This is a
frozen engineering rerun, **not fresh independent out-of-sample confirmation**.
Rule calendars, current-vintage metadata, EOD reference fills, zero cash yield
and 10%/20% gross reserve proxies retain the [research limitations](COMMODITY_RESEARCH.md).
There is no historical SPAN, intraday margin-call or physical-delivery guarantee.

See [paired-retirement tests](../tests/test_commodity_staged_exit.py),
[earlier execution comparison](COMMODITY_EXECUTION.md),
[validation record](VALIDATION.md) and [data rights](../DATA_RIGHTS.md).
Research was directed by Mingju Zhang; implementation and experiments were
AI-assisted. Unaided personal review is tracked separately from automated tests.
