# Intraday verification — 30 October 2026

The complete project was installed in a new Python 3.12 environment with its compatible locked dependencies. **152 tests passed**, including six additional intraday tests. The default allocation entry point and all six intraday synthetic variant/delay runs completed. Existing commodity and allocation code was retained.

Intraday checks cover signal-to-quote ordering, cash reconstruction, identical past output after perturbing future data, missing exit quotes with retained risk, rejected endpoint look-ahead, early-close handling, partial fills, funding and duplicate timestamps. The synthetic result is an execution fixture, not estimated market performance. All six declared fixture runs lose money; none were removed.

Five fixed licensed-data audit dates were extracted across old/new schemas, an early close and a high-volatility session. The optimized query agrees with the original successful pilot outputs. Observed missing-field and timeout failures remain in the private audit. Full historical coverage, corporate actions, cash-rate availability and source exceptions must pass separately before a historical performance report is released.

[Data gates](INTRADAY_DATA_STATUS.md) · [Protocol](INTRADAY_PROTOCOL.json) · [Tests](../tests/test_intraday.py) · [Synthetic results](../reports/intraday-synthetic/REPORT.md) · [Current CI](https://github.com/Mingju-Zhang-CBS/systematic-strategy-lab/actions)
