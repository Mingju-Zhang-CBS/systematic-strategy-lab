# Intraday verification — 30 October 2026

The complete project was installed in a new Python 3.12 environment with its compatible locked dependencies. **152 tests passed**, including six additional intraday tests. The default allocation entry point and all six intraday synthetic variant/delay runs completed. Existing commodity and allocation code was retained.

Intraday checks cover signal-to-quote ordering, cash reconstruction, identical past output after perturbing future data, missing exit quotes with retained risk, rejected endpoint look-ahead, early-close handling, partial fills, funding and duplicate timestamps. The synthetic result is an execution fixture, not estimated market performance. All six declared fixture runs lose money; none were removed.

Five fixed licensed-data audit dates were extracted across old/new schemas, an early close and a high-volatility session. The optimized query agrees with the original successful pilot outputs. Observed missing-field and timeout failures remain in the private audit. Full historical coverage, corporate actions, cash-rate availability and source exceptions must pass separately before a historical performance report is released.

[Data gates](INTRADAY_DATA_STATUS.md) · [Protocol](INTRADAY_PROTOCOL.json) · [Tests](../tests/test_intraday.py) · [Synthetic results](../reports/intraday-synthetic/REPORT.md) · [Current CI](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions)

## Source and cash extension — 31 October 2026 UTC / v0.10.1

A new Python 3.12 environment installed the locked dependencies and built package; **167 tests passed**, dependency checks succeeded, and the default allocation and both intraday demonstrations ran. The original six execution-fixture numerical results were unchanged. Additional checks cover dated identities, cash/split units, missing or same-day action clocks, future-event perturbation, mixed CSV timestamp precision, cash publication timing, DST day counts and independent funding reconstruction.

The independent order audit reconstructs financing and borrow charges rather than accepting the engine's reported charges as inputs. It handles zero-admitted-share quote attempts separately from actual fills. Private partial-ledger outputs were also reproduced with the installed package; their source-derived details remain private. A successful accounting check does not turn a stopped/source-gated prefix into a completed historical study. See the [source-audit methods](INTRADAY_SOURCE_AUDIT.md) and [invented known-answer examples](../reports/intraday-data-fixture/REPORT.md).

The source adapter's synthetic 2-for-1 case validates arithmetic and input gates. It does not establish an observed split event, complete original-release histories or universal corporate-action treatment. These are automated checks, not unaided human replication or a profitability claim.
