# Allocation study: local validation record

Validated on 2026-11-01 using Python 3.12.6 / Windows. This record covers local
source and independent installed-wheel checks. Published-head cloud checks are
available from the repository's [Actions page](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions).

## Numerical and temporal tests

The complete repository suite passed **253 tests**, including 33 new allocation
cases. A fresh virtual environment with system-site packages disabled installed
the locked dependencies and the built 0.12.0 wheel. All 253 tests passed again
from copied tests outside the source tree, importing the installed package.
`pip check` reported no broken requirements. Upstream Matplotlib/pyparsing
deprecation warnings were retained.

Known answers check diagonal BL posteriors, zero-confidence reference weights,
named relative views against an independent precision formula, tau cancellation,
asset permutation, mean-sensitive utility and mean-independent minimum variance.
Risk-budget checks cover inverse-volatility weights with diagonal covariance,
binding-cap residuals, contribution identities, zero return tilt and scale
normalization. Forged success flags, rejected solvers, missing sessions and
deliberate failure/cash paths are exercised.

Changing future prices leaves earlier target schedules, event records and
parameter snapshots exactly unchanged. An early test found that pandas memory
layout could change covariance rounding at roughly `3e-17`. Canonical contiguous
arrays and single-thread estimation fixed this before any performance run;
the strict prefix test now passes. This was a numerical reproducibility repair,
not parameter selection from historical returns.

## Fixed invented experiment

The source and independent-wheel runs each produced all 138 accounts, 552 metric
rows and 144 paired interval rows. All **443 CSV files were byte-identical**;
all **3,726 successful parameter snapshots** matched exactly. The report and
all three figures were also byte-identical. The protocol was recorded before
performance execution; no specification was selected or dropped by results.

The [standalone audit](../tools/verify_allocation_run.py) imports no account or
optimizer implementation. It reconstructs units from trades and cash from
discounted signed flows, costs and calendar-day interest, then independently
checks equity, price P&L, held weights, execution dates and after-fee targets.
All 138 invented accounts reconciled; the largest observed residual was about
`1.78e-9` model dollars. This checks accounting, not actual ETF execution or alpha.

The [public snapshot](../reports/allocation-synthetic/SNAPSHOT.md)
contains 38 files and 37 artifact hashes. Deterministic gzip files retain their
decompressed original-run fingerprints. All complete metric and interval rows,
events, parameters and forecast perturbations remain represented; six primary
base-case accounts are retained for direct audit. The snapshot audit checks
all retained hashes and reconstructs those six accounts. Other account details
can be regenerated from the full demo; the snapshot does not pretend to contain
all 450 original generated files.

Separate real-reference input, complete outputs, repeated-run comparisons and
audit receipts remain private. Real prices, fitted parameters and derived
findings do not appear in this public validation record.

## Recheck

```bash
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest
python -m strategy_lab.allocation --demo --output local-runs/allocation
python tools/verify_allocation_run.py local-runs/allocation
python tools/verify_allocation_run.py reports/allocation-synthetic
```

Use a fresh output directory. Source/shared-code fingerprints, frozen protocol,
generated artifacts, relative document links and the displayed invented figures
were checked. The configured workflow includes the allocation demo and audit;
configuration alone is not a successful cloud run. Read the
[methods and limitations](ALLOCATION_RESEARCH.md) before interpreting results.
