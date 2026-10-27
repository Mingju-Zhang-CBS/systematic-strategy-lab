# Curve hypotheses and the evidence gate

The commodity extension now includes a **monthly signal calculation** alongside
the [fixed-pair accounting diagnostic](COMMODITY_ACCOUNTING.md). Neither is a
completed historical commodity strategy study. The existing real TSP study has
its own data, account and results; its conclusions do not transfer to futures.

## From a curve to a falsifiable question

For positive near/far prices, curve carry is
`365 / maturity_gap_days × log(near_price / far_price)`. A downward-sloping
curve has positive carry under this convention. Storage, seasonality, financing
and risk compensation can affect that slope. It is not an observed spot basis,
an identified convenience yield, or a guaranteed return from rolling a contract.

Trend is the sign of the near-contract rolling strategy's compounded returns
over **12 complete months**. Basis-momentum is the near strategy's compounded
12-month return minus the corresponding far strategy's return. The distinction
matters: today's dollar spread is a level; basis-momentum describes differences
in past return histories. This independently specified eight-product study is
informed by [Boons and Porras Prado (2019)](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12738),
but does not claim paper-exact replication. A detailed comparison of the paper's
roll/sample conventions remains required before historical experiment freezing.

Predeclared directions are long-only N1; near-contract trend; top-two/bottom-two
carry; top-two/bottom-two basis-momentum outright; and near/far opposite signs
from basis-momentum. Cross-sectional requests require at least six eligible
products. Ties use ascending product code, independent of row order. The signed
spread request uses equal physical contract counts; it is not risk-free or
automatically notional-neutral.

## Run the offline numerical example

```text
python examples/explain_curve_signals.py
python -m pytest tests/test_commodity_signals.py
```

The example invents all monthly observations. The output contains directions,
not quantities, Sharpe ratios or funded trading performance.

`strategy_lab.commodities.signals.monthly_candidates` takes monthly near/far
rolling returns, eligible curve snapshots, the completed month and a timezone
aware decision cutoff. An explicit availability timestamp selects visible
versions only. Missing months are retained as incomplete histories. Nonpositive
prices disable logarithmic carry; invalid returns disable the affected return
signal. These exclusions do not delete the underlying market stress episode.
Future observations and later revisions cannot change earlier signal outputs.

**Upstream accounting is essential.** A rolling return must mark yesterday's
held contract at both endpoints, close it, and establish the replacement at its
own reference. A jump between two delivery prices is not a holding profit.
Every scheduled holding interval must be represented. Missing marks cannot be
bridged or dropped to manufacture a complete monthly return. No certified
historical return ladder is bundled with this signal interface.

## What must precede a historical results table

Historical WRDS/LSEG extraction and a bounded real-reference cash reconciliation
are maintained privately. The full study has **not passed data admission**:
complete historical settlement calendars, early first-notice coverage,
first-position boundaries and publication vintages remain incomplete. A current
vendor snapshot and an imposed lag cannot establish full point-in-time history.
Missing front-contract evidence must not silently promote a distant maturity.

Actual historical margin observations have not been obtained from the queried
WRDS margin table. [CME's historical margin directory](https://www.cmegroup.com/solutions/risk-management/margin-services/historical-margins.html)
offers additional evidence, including separate pre/post-SPAN2 energy files;
rolling bucket codes and margin definitions require verification before account
use. The 10% base/20% stress reserve remains a **model collateral proxy**, with
no spread offsets, rather than observed exchange or broker margin. Collateral
encumbers cash; variation margin and costs change equity.

A complete funded study still requires the historical adapter, complete return
ladder, equal-risk integer allocation, fixed execution controls and paired
inference. Missing/failed paths and nonsignificant comparisons will remain in
the report. No full-history commodity alpha, prospective out-of-sample success
or real trading is claimed. Source prices, per-contract outputs and private
derived results are excluded pending applicable release rights; see
[Data Rights](../DATA_RIGHTS.md).
