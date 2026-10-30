# Before opening, budget the exit

A position can satisfy today's entry allowance yet leave too little time to
retire before its delivery boundary. This revision links proposed additions to
the existing paired-retirement protocol. The same fixed assumptions govern
both decisions. All earlier baselines, failures and reports remain available.
Public examples are **invented**; licensed source data and all real derived
findings remain private.

See the [post-admission stress study](COMMODITY_STRESS.md) for capacity surprises
and announced proxy-collateral increases after entry. This admission baseline
remains unchanged and separately reproducible.

## Two protocols, one controlled change

|Policy|Held-inventory retirement|Proposed additions|
|---|---|---|
|`capacity_exit`|Capacity-sized paired slices, persistent goals, fixed early trigger|Original entry checks|
|`entry_budget`|Unchanged|Also test full post-trade exposure against an exit-time budget|

```text
python -m strategy_lab.commodities.research_report --fixture --policy entry_budget --output local-runs/admission
python -m strategy_lab.commodities.research_report --fixture --policy capacity_exit --output local-runs/retained
python -m pytest tests/test_commodity_entry_budget.py
python examples/explain_entry_budget.py --output local-runs/admission-cases
```

The primary study retains the same eleven scenarios, five strategies and two
separately funded benchmark sleeves. The complete old 77-path experiment must
reproduce numerically. Selection, reference histories, signals, cost assumptions,
risk sizing, calendar proxy and hard delivery deadlines are unchanged. The
default CLI remains `legacy` for compatibility. For licensed inputs replace
`--fixture` with `--input PRIVATE_INPUT`, keeping its outputs private unless
publication is permitted.

See [new invented results](../reports/commodity-entry-budget-synthetic/REPORT.md),
[controlled admission cases](../reports/commodity-entry-budget-synthetic/controlled-admission/REPORT.md)
and the [retained retirement report](../reports/commodity-staged-exit-synthetic/REPORT.md).

## Which requests are tested?

Test a fresh entry, replacement, sign reversal or increase in absolute exposure.
Use the **total target position**, not only the added contracts. For example,
moving from ten to fourteen units requires a budget to retire fourteen, not
four. A two-leg calendar spread uses equal integer units, the earliest candidate
leg deadline under the retained convention, and the smaller leg allowance.

Plain reductions are not subject to admission. A refused replacement cannot
block an outgoing close or restore its old exposure after that close succeeds.
Pending old exits continue under the original latched goal. The gate rejects
the entire addition; it does not shrink requests to a conveniently successful
quantity, rerank signals or redistribute rejected risk to other products.
Every later proposal is reconsidered using its newly permitted observations.

## One information clock, one strict budget

At 07:00 Chicago on decision day d, use five scheduled observations ending d−2.
For each candidate leg, compute `floor(1% × volume)` on each observation. The
conservative unit allowance is the minimum across observations and legs;
missing activity gives zero. Current-day price or activity cannot improve it.

Entry books at today's EOD reference. The first retirement decision is the
**next scheduled session**, so entry day is not credited as an exit day. Let:

- `remaining = earliest_hard_deadline_index − decision_index`;
- `drain = ceil(total_target_units / conservative_capacity)` when capacity is positive.

Admit only if all are true:

1. Conservative capacity is positive.
2. `remaining > 10`, the unchanged retirement lead.
3. `remaining > drain + 2`, using the unchanged two spare sessions.

Strict inequalities mirror the existing held-inventory trigger, which retires
when its corresponding quantity is less than or equal to the threshold.
Equality is refused. This is a consistency rule under a fixed capacity
projection; it does not reserve real future liquidity or certify a fill.

The hard deadline still subtracts the original five scheduled sessions from
the known FND/LTD boundary, or ten in that predefined stress. First-position
history, original release vintages and unexpected settlement closures are not
manufactured by this extra check.

## Refusal is separate from execution

Signals and risk sizing first produce the frozen target. Retirement planning
uses that original target. If admission fails, the opening phase falls back
only to the already frozen reduction result: keep a reduced old position or
remain flat, never re-enter retired inventory. This preserves the sequence
"all portfolio reductions, then optional additions."

Passing the gate does not override a pending exit, a missing execution reference,
zero activity, cumulative daily side capacity, stale-mark risk restrictions or
post-mark funding. Both spread legs must execute together as modeled paired
slices. Closing and reopening an overlapping contract consumes both sides'
capacity and costs. Rejected requests incur no invented fill cost.

Each account exports `entry_admissions.csv.gz`: decision/observation dates,
candidate contracts, current and total target units, deadline, available exit
sessions, conservative capacity, projected drain, individual check flags,
admission and all refusal reasons. This is **intent and qualification**, not a
trade log. Compare it with exit plans, fills, holdings, rejections and cash.

## Replaying a known failure without overstating causality

Use the exact retained proposal, information window and deadline to replay one
admission decision with the same function used by the engine. Separately rerun
the entire account from its original starting date. Earlier refusals change
capital, exposure and later integer requests, so the new historical account may
not reach the same state. A fixed-state refusal verifies the rule; it does not
prove a hypothetical P&L contribution from one avoided trade.

The gate is frozen before revised strategy results. The lead, five-observation
window, participation rate, spare sessions, sample and signal parameters are
not selected for returns. Negative results, new failures and nonsignificance
remain in the reports. The history has already been inspected: all phase
labels are historical diagnostics, not fresh independent out-of-sample evidence.

See [retirement methods](COMMODITY_STAGED_EXITS.md),
[admission tests](../tests/test_commodity_entry_budget.py),
[validation](VALIDATION.md) and [data rights](../DATA_RIGHTS.md). EOD paired fills,
scheduled calendars and 10%/20% gross reserve proxies remain assumptions rather
than order-book reconstruction, historical SPAN or a delivery guarantee.
Research choices were directed by Mingju Zhang; implementation and experiments
were AI-assisted. Unaided personal review is tracked separately.
