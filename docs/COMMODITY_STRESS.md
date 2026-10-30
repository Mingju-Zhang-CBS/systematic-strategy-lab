# An admitted position has not reserved its exit

Entry admission tests a projection. It cannot guarantee future capacity or
collateral. This study fixes adverse conditions **after** admission, retaining
the existing prices, signals, costs, risk model, entry gate and delivery boundary.
All public results are invented examples; licensed real inputs, their event
schedules and all derived real findings remain private.

## Freeze the question before the results

The retained `entry_budget` baseline contains eleven scenarios and seven funded
accounts per scenario. It remains independently reproducible, along with every
earlier stopped path. The stress study uses its seven base accounts and the
previously reviewed three-session-later carry account: eight funded accounts.

For each account, select the first **actual risk addition** per product and
calendar year from ordered baseline fills. An increase or sign reversal counts;
an unfilled proposal does not. Fix that date and those contract IDs before
stress results. Start the shock on the next scheduled session and keep it for
five sessions. Do not move an event when the stressed account has different
inventory. Unexposed events remain in the schedule and in the private exposure
audit. Subsequent P&L is a full changed-account result, not a single-entry effect.

|Case|Capacity fraction|Gross reserve multiplier|Affected members|
|---|---:|---:|---|
|Control|1|1|No shock|
|Half capacity|0.50|1|Both fixed cohort contracts|
|Quarter capacity|0.25|1|Both|
|One-leg quarter capacity|0.25|1|Last frozen fill member; the only leg for an outright|
|Zero capacity|0|1|Both|
|Double reserve|1|2|Portfolio reserve during the window|
|Combined|0.25|4|Both cohort contracts, plus portfolio reserve|

Seven cases × eight accounts = **56 paths**, sharing markets and assumptions;
they are not 56 independent statistical observations. These magnitudes and
durations are hypothetical stress assumptions, not historically calibrated
market supply, exchange margin changes or return-selected thresholds. Overlaps
use the smallest capacity factor and largest reserve multiplier, not products
of successive shocks. No favorable scenario replaces the control.

## Keep three clocks distinct

1. **Observation:** planning uses the existing five scheduled observations
   ending d−2. A historical offer factor becomes available on that same delayed
   clock; it cannot disclose a current or future shock.
2. **Decision:** at 07:00 Chicago, today's reserve multiplier is assumed publicly
   announced. It can affect sizing and a margin-driven reduction, using known
   lagged equity and the existing trailing price basis. Current EOD prices and
   offered capacity remain unknown.
3. **Execution:** the current capacity offer can constrain actual modeled fills.
   A surprise can reduce a frozen request, but cannot retroactively improve its
   admission or signal.

Do not rewrite source volume to pretend these scenarios happened. Instead,
`b[t] = floor(participation × historical_volume[t])` and
`known_capacity[t] = floor(b[t] × offer_factor[t])`. Today's cumulative side
allowance is:

```text
min(known_capacity[d−2], floor(b[d−2] × current_offer_factor[d]))
```

Participation is included once. Closing and reopening share this same limit.
The lagged restriction can persist briefly after supply recovers. Missing
activity and missing execution references still prevent a fill. None of these
limits reconstructs order-book depth, queue position, intraday credit or an
observed exchange spread fill.

## Preserve paired exits when supply is smaller than the request

Suppose a frozen reduction requests three spread units. At execution, the near
member can supply four and the far member only one: fill **one paired unit**,
pay both legs' costs, retain the remaining goal, and do not open replacement
risk until that goal is met. If either member has no capacity, fill neither.

Keep `exit_plans` as the original request and `trades` as the realized modeled
slice; they are deliberately different records. Optional additions remain
whole-request all-or-none. Rejecting an addition never undoes an outgoing close.
The same hard deadline still stops unretired inventory; there is no hidden
liquidation, grace-period extension or capital reset to rescue a path.

## A risk buffer is different from a cash shortfall

The original reserve is 10% of the gross marked proxy, with no spread offsets.
A multiplier of two means 20%; four means 40%. These are **proxy reserves**,
not historical SPAN, maintenance margin or a broker's actual collateral rule.

When the announced rate and known lagged gross exceed the existing 50%
reserve/equity risk buffer, request proportional integer reductions of current
inventory. Both spread members use the same scale. Block additions until this
reduction target is met; capacity may prevent it. Actual post-mark funding
checks remain in force. At EOD:

- Reserve above 50% but no greater than cash is a risk-buffer breach. Keep the
  breach and outstanding reduction visible; do not automatically call it insolvency.
- Reserve greater than all cash stops as `failed_proxy_collateral_shortfall`,
  unless an earlier stopping reason already applies. All failure events remain.
  There is no assumed external cash injection.
- Reserve is an encumbrance: `free_cash = equity − reserve`. Equity still equals
  opening equity plus variation margin minus actual per-leg costs. Do not debit
  reserve as another P&L expense or spend futures notional principal.

The EOD convention does not simulate an intraday margin call or legal close-out
process. Lagged sizing and subsequent price changes can also leave a breach;
the report does not erase that timing mismatch.

## Inspect shortages before interpreting returns

Each stressed account exports:

- `stress_windows.csv`: all fixed events, affected contracts and assumptions;
- `stress_budgets.csv.gz`: pre-fill held units, known conservative capacity,
  current offered full-day limit, remaining sessions, projected drainage, spare
  time and zero-capacity flags;
- `stress_sessions.csv.gz`: effective rate, target reduction scale, risk-buffer
  breach, cash shortfall and affected held contracts;
- the original admissions, exit plans, ordered fills, holdings, variation margin,
  cash ledger and independent terminal reconciliation.

Zero projected capacity has no finite drainage/slack: its flag is retained,
not converted to zero time. These are dependent product-day checks, not a
count of independent experiments. Pairing, cumulative capacity, event clocks,
collateral identities and source-to-output linkage require separate checks.

The original two economic comparisons and 6/12-month blocks remain. An
incomplete or stopped required account makes the comparison not evaluable;
months are not silently discarded. Already-inspected history is not new
independent OOS. Negative and nonsignificant findings remain in the report.

## Reproduce and review

The bundled fixture retains its original small risk positions and liquid source
volumes. Many capacity cuts need not bind in that example; an all-completed
fixture is not an assurance about market resilience. Constructed invariant
tests separately force partial paired reductions, unavailable supply and a
collateral cash shortfall. We do not recalibrate the fixture to manufacture a
dramatic performance result after seeing it.

```bash
python -m pytest
python -m strategy_lab.commodities.stress_report --fixture --output local-runs/stress
python -m strategy_lab.commodities.research_report --fixture --policy entry_budget --output local-runs/retained
```

[Invented stress results](../reports/commodity-stress-synthetic/REPORT.md) ·
[Stress invariants](../tests/test_commodity_stress.py) ·
[Admission protocol](COMMODITY_ADMISSION.md) ·
[Validation](VALIDATION.md) · [Data rights](../DATA_RIGHTS.md).

For separately licensed work, supply `--input PRIVATE_INPUT --cohorts
FROZEN_PRIVATE_CSV` instead of `--fixture` and keep the output private. Scheduled
calendars, current-vintage contract evidence and missing first-position archives
retain their earlier limitations. Research direction was selected by Mingju
Zhang; engineering and experiments were AI-assisted. Unaided personal review is
tracked separately from automated execution.
