# Intraday verification — 30 October 2026

The complete project was installed in a new Python 3.12 environment with its compatible locked dependencies. **152 tests passed**, including six additional intraday tests. The default allocation entry point and all six intraday synthetic variant/delay runs completed. Existing commodity and allocation code was retained.

Intraday checks cover signal-to-quote ordering, cash reconstruction, identical past output after perturbing future data, missing exit quotes with retained risk, rejected endpoint look-ahead, early-close handling, partial fills, funding and duplicate timestamps. The synthetic result is an execution fixture, not estimated market performance. All six declared fixture runs lose money; none were removed.

Five fixed licensed-data audit dates were extracted across old/new schemas, an early close and a high-volatility session. The optimized query agrees with the original successful pilot outputs. Observed missing-field and timeout failures remain in the private audit. Full historical coverage, corporate actions, cash-rate availability and source exceptions must pass separately before a historical performance report is released.

[Data gates](INTRADAY_DATA_STATUS.md) · [Protocol](INTRADAY_PROTOCOL.json) · [Tests](../tests/test_intraday.py) · [Synthetic results](../reports/intraday-synthetic/REPORT.md) · [Current CI](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions)

## Source and cash extension — 31 October 2026 UTC / v0.10.1

A new Python 3.12 environment installed the locked dependencies and built package; **167 tests passed**, dependency checks succeeded, and the default allocation and both intraday demonstrations ran. The original six execution-fixture numerical results were unchanged. Additional checks cover dated identities, cash/split units, missing or same-day action clocks, future-event perturbation, mixed CSV timestamp precision, cash publication timing, DST day counts and independent funding reconstruction.

The independent order audit reconstructs financing and borrow charges rather than accepting the engine's reported charges as inputs. It handles zero-admitted-share quote attempts separately from actual fills. Private partial-ledger outputs were also reproduced with the installed package; their source-derived details remain private. A successful accounting check does not turn a stopped/source-gated prefix into a completed historical study. See the [source-audit methods](INTRADAY_SOURCE_AUDIT.md) and [invented known-answer examples](../reports/intraday-data-fixture/REPORT.md).

## Fine-clock and publication evidence — 30 October 2026 New York / v0.10.2

A noneditable installation in a separate Python 3.12 environment passed **186 tests** and dependency checks. The new evidence report, original intraday demonstrations, cash/action examples and default allocation entry point ran from that installed package. The strategy engine's bytes remain unchanged from v0.10.1.

Nineteen evidence cases cover nanosecond reconstruction, lot conversion, quote conditions, incomplete tuple matches, rounding ties, sequence scopes, explicit timezones, order-window boundaries, future-cluster perturbation and publication facts that cannot be admitted. Fine-clock recovery does not change the original arrival/deadline contract. Printed document dates and distribution schedules do not become verified amount-release timestamps.

[Precision and publication methods](INTRADAY_EVIDENCE.md) · [Invented evidence report](../reports/intraday-evidence-fixture/REPORT.md) · [Evidence tests](../tests/test_intraday_evidence.py). Licensed replay results and their retained source failures are private; a successful reconstruction still does not establish completed long-history performance.

The source adapter's synthetic 2-for-1 case validates arithmetic and input gates. It does not establish an observed split event, complete original-release histories or universal corporate-action treatment. These are automated checks, not unaided human replication or a profitability claim.
