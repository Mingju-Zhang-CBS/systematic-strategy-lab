# Resume-ready project statements

Use one or two bullets according to the role. These describe **modeled allocations on actual public fund NAVs**, not live trading, ETF execution or prospective alpha. Numerical evidence: [real report](../reports/real/REPORT.md), [metrics](../reports/real/metrics.json), [protocol](../strategy_lab/data/protocol.json) and [validation](VALIDATION.md).

## Investment research / buyside quant

- Engineered a reproducible multi-asset allocation study on 5,639 official public fund-NAV dates, comparing momentum with a shared-risk-budget static control under frozen publication, reallocation and funding rules.
- Evaluated chronological development, validation and 2020–2025 confirmation windows across nine cost/delay stresses; retained a −0.42 pp annualized paired log-return difference and a 95% block interval spanning zero rather than claiming alpha.

## Quantitative research / financial data science

- Built past-only momentum and trailing-covariance features with explicit observation, assumed-publication, request and posting clocks; validated future-price invariance, keyed date pairing and deterministic block uncertainty in 23 tests.
- Packaged a rights-documented public NAV snapshot, source/configuration fingerprints, daily ledgers and five research figures for offline Python 3.12 reproduction and CI.

## Markets / S&T / portfolio solutions

- Modeled whole-percent fund reallocation with unknown-at-request posting NAVs, long-only funding and two-leg transaction-friction stresses; reconciled 21,472 daily account rows across four strategies.
- Distinguished accumulation-NAV income from cash dividends and embedded fund expenses, using worked cash-flow examples and cost/latency sensitivities to explain portfolio implementation and product constraints.

## Evidence and phrasing boundaries

The 5,639 dates are raw common data rows; 5,368 are evaluation rows per strategy after the fixed start/warmup, giving 21,472 account rows. The confirmation comparison uses 1,495 paired dates. The −0.42 pp figure is an annualized **mean log-return difference**, not alpha, a CAGR spread, a guaranteed loss or an investment recommendation. The 20-session 95% interval is [−3.23, +2.33] pp; 63-session inference is also reported. The 23 tests include six preserved synthetic-accounting tests and 17 real-study test cases. Do not call all seven portfolio studies real-data strategies or claim this project proves commercial execution capacity.
