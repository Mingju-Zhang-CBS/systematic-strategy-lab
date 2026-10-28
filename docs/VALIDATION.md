# Validation record and interpretation

## Temporal checks

No price after an observation date enters its momentum or covariance calculation. The code distinguishes the valuation date, an assumed publication-completion date, the frozen request time and the posting date. A request at 11:00 New York time uses percentages determined before that day's NAV is known. Mutation tests change future NAVs and verify that earlier decisions and ledger rows remain unchanged; a separate test changes the posting NAV and verifies that the frozen target survives while executed units change.

There is no random train/test split, full-sample scaler, imputation or model search. The strategy is fixed; trailing covariance estimation is its only fitted component. Development, validation and confirmation are chronological reporting windows, with continuous holdings. A strategy specification recorded before this implementation's return calculation is not independent proof against prior familiarity with markets. Current-vintage historical revisions and unavailable publication timestamps remain unresolved data limitations.

## Economic checks

- Accumulation NAV income is counted once. An artificial 2% NAV income event produces 2% wealth growth without an extra dividend credit.
- A two-fund transfer pays hypothetical friction on both legs. After-fee holdings plus fee equal pre-transfer value.
- Every day satisfies prior NAV + embedded-income valuation P&L − fees = closing NAV.
- Long-only holdings, fully funded weights, whole-percent target allocations and posting-month transfer counts are checked.
- The reserve earns only the G NAV return. No separate cash interest or operating-expense debit is added.
- No-op transfers incur no fee; higher friction reduces passive terminal wealth on the same path.
- Starting-period losses enter maximum drawdown. Paired inference rejects different date grids and is deterministic under its recorded seed.
- The unchanged synthetic accounting suite separately checks raw split units, ex-date receivables and delayed dividend payments. It is not used as evidence of real ETF performance.

## Reproduction

Python 3.12, the locked dependency closure, tests, both offline studies and both numerical examples are exercised by [GitHub Actions](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions/workflows/checks.yml). The release also checks an installed wheel outside the source tree so that missing data package files cannot be hidden by an editable checkout. Run manifests bind source hashes, data hashes, protocol, configuration, package versions and generated outputs. Timings and sampled RSS are machine-specific and cover the experiment loop; report plotting and writing are outside that timed section.

See the [real report](../reports/real/REPORT.md), [frozen protocol](../strategy_lab/data/protocol.json), and [tests](../tests/test_real_research.py). Checks establish the modeled accounting and information contract; they cannot recover an unavailable historical revision archive or prove actual execution.
## Commodity extension — separate acceptance record

The original TSP/legacy checks above are preserved. The commodity extension adds
29 synthetic checks covering eight products, paired integer quantities, cash and
reserve conservation, roll-gap exclusion, delivery boundaries, calendar closures,
lagged capacity, missing references, negative prices, insolvency, changing units
and future-information perturbation. The stage-2 repository suite totaled **52**.
The independent wheel and offline demo receipt is recorded in the release
evidence; CI also runs the full commodity fixture command.

Tests certify the declared mechanics on constructed inputs, not historical
exchange-calendar correctness, actual broker margin or executable fills. The
[input contract](COMMODITY_INPUTS.md) requires those upstream evidence checks.

### Monthly hypothesis interface

Twelve additional [synthetic checks](../tests/test_commodity_signals.py) cover
12-month compounding, future observations and later revisions, missing-month
retention, nonpositive carry inputs, a six-product sorting minimum, separate
near/far history eligibility, deterministic ties and impossible input clocks.
The stage-3a complete suite passed **64 tests**. The offline
[curve example](../examples/explain_curve_signals.py) reports directions only.
These checks do not certify a historical rolling-return ladder or a funded
carry/trend/basis-momentum result; see the [evidence gate](COMMODITY_SIGNALS.md).

### Exploratory funded runner

Fourteen further [constructed-input checks](../tests/test_commodity_research.py)
cover scheduled-calendar conventions, blocked front notice/specification
evidence, same-contract roll returns, cents and negative prices, funded pairing,
independent terminal cash reconciliation, future-data perturbations, execution
reference isolation, retained exit/capacity failures, zero-exposure and invalid
month inference, centered paired comparisons and the t−2 input boundary.
The stage-3b repository suite passed **78 tests**, including the original 23.
An independent wheel installation passed the same suite; all 269 generated
synthetic CSV/gzip artifacts match the source run byte-for-byte in the recorded
Python/numpy/pandas environment. Rendering dependencies and wall time can vary.
The [full offline report](../reports/commodity-research-synthetic/REPORT.md) is
invented data throughout; no licensed market-data result is certified by CI.

### Exit-priority and persistent-liquidity revision

Six further [invariant tests](../tests/test_commodity_exit_priority.py) cover a
rejected replacement with a feasible old close, a genuinely unfillable old
exit, atomic old-spread closure, paid overlap round trips, cumulative side
capacity, portfolio-wide reduction priority, five consecutive observations,
monotone maturity floors, future-activity perturbation and policy validation.
The stage-4 complete suite passed **84 tests**, both from source and from a
separately installed Python 3.12 wheel. All **269** generated persistent-policy
synthetic CSV/gzip files match those two installations byte for byte. Locked
Matplotlib dependencies emit 14 upstream deprecation warnings; tests pass.

The previous 77-path baseline is retained and its numerical outputs are checked
privately against the revised default legacy engine; added selection-policy
columns are distinguished from changed calculations. The
[new invented report](../reports/commodity-exit-priority-synthetic/REPORT.md) and
[original invented report](../reports/commodity-research-synthetic/REPORT.md)
remain separate, with their own source/configuration/output fingerprints.
CI runs both full offline policies. Passing accounting tests does not certify
real execution capacity, historical margin or an incremental strategy premium.

### Capacity-sized paired retirement

Ten further [constructed-market tests](../tests/test_commodity_staged_exit.py)
check cross-day goal persistence, weaker-leg paired slices, rejection when one
leg lacks a reference, retained zero-capacity boundary failure, early-lead and
drain-budget triggers, maturity lockout, execution-reference isolation, future
perturbation and shared capacity after the last old slice. The complete suite
passes **94 tests** from source and from a separately installed Python 3.12
wheel. All **346** synthetic CSV/gzip artifacts match byte for byte, including
77 account-level exit-plan files. The locked plotting stack retains 14 upstream
deprecation warnings; tests pass.

The complete previous persistent-policy experiment is retained separately;
its 77 summary rows and 269 CSV/gzip artifacts are checked for exact reproduction.
New [invented results](../reports/commodity-staged-exit-synthetic/REPORT.md)
record planned versus executed paired reductions. CI runs the original coupled,
persistent and capacity-retirement offline studies. None of these checks
certifies a quote-level fill, a historical SPAN series or a profitable premium.

