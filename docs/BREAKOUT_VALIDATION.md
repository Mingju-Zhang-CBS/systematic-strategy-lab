# HMM breakout transfer: validation record

Local validation on 2026-11-01 used Python 3.12.6 / Windows. The full repository
suite passed **280 tests**, including 27 new breakout cases. A new virtual
environment with system-site packages disabled installed locked dependencies
and the built 0.13.0 wheel. Copied tests outside the source tree passed all 280
checks again, importing the installed package. `pip check` found no broken
requirements. Fourteen upstream Matplotlib/pyparsing deprecation warnings in
the isolated test run were retained.

Known answers check exclusion of current-bar highs/lows, strict comparisons,
carried versus pulse positions, independent channel memory during HMM failure,
gate recovery without a new breakout, volatility caps, common parent controls,
interaction arithmetic and invalid/incomplete OHLC. Future-bar perturbations
leave past channel targets unchanged; an actual-estimator prefix test also
checks earlier HMM probabilities, refit records, fitted snapshots and targets.
Existing parent tests retain exhaustive forward-probability answers, train-only
normalization, refit-boundary filtering and funded next-close accounts.

The frozen protocol was recorded before any breakout performance calculation.
No HMM source leaf, feature, parameter, gate or failure rule changed. In the
complete invented source experiment, both assets' probabilities and all 324
fitted parameter snapshots match the bound parent exactly. All 24 shared
control ledgers (2 assets × 2 methods × 6 scenarios) are byte-identical to the
parent. The matching process checks parent input/protocol/source/artifact
fingerprints first; environment warning text is excluded from numerical model
equivalence. See [the receipt](../reports/breakout-synthetic/parent_equivalence.json).

The independent installed-wheel invented experiment reproduced all **661 CSV
files byte for byte**, all 324 fitted snapshots exactly, and the report and
three figures byte for byte. Dependency versions and frozen shared-source
fingerprints also matched the source run.

Each complete experiment produces 216 accounts, 864 metric rows and 480 paired
interval rows. The [standalone audit](../tools/verify_breakout_run.py) imports no
strategy, HMM or account engine. It reconstructs units from signed trades and
cash from discounted cash flows, costs and calendar-day interest, then checks
NAV, P&L, held exposure, drift-adjusted turnover, requested after-fee targets,
first-day cash, next-session timing and unexecuted final requests. All 216
invented source accounts reconciled; the largest observed reconstruction
residual was approximately 3.05e-9 model dollars. Paired-mean arithmetic is
checked independently against the retained ledgers. Correct accounting does
not establish actual ETF execution or market alpha.

The compact [public snapshot](../reports/breakout-synthetic/SNAPSHOT.md) contains
59 files and 58 artifact hashes, including 48 deterministic gzip files with
decompressed original-run fingerprints. It retains every metric/interval,
both assets' signals/features/targets/states/models, and 12 primary base-case
accounts. Its audit reconstructed all 12 accounts (largest residual about
1.05e-9); other cost/cash and sensitivity ledgers can be regenerated offline.
All three displayed invented figures were visually inspected.

Separate real input, model snapshots, outputs, audits and interpretations stay
private. No real prices, fitted real models or derived real results appear in
this public record. Full installed-wheel experiment comparisons are recorded
locally before publication.

Recheck with the commands in [methods](BREAKOUT_RESEARCH.md). The configured
GitHub workflow runs the full suite, creates the parent and transfer demos,
and audits the transfer accounts. Published-head outcomes are available on
[Actions](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions);
workflow configuration alone is not a successful cloud run.
