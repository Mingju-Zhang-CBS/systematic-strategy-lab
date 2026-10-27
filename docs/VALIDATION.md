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
The current complete suite passes **64 tests**. The offline
[curve example](../examples/explain_curve_signals.py) reports directions only.
These checks do not certify a historical rolling-return ladder or a funded
carry/trend/basis-momentum result; see the [evidence gate](COMMODITY_SIGNALS.md).

