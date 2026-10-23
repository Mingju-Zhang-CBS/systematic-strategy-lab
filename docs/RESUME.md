# Resume drafts and evidence

Use after reviewing the code, reproducing the study and being able to explain it. Development was AI-assisted. These drafts describe the new portfolio implementation, not an employer assignment, actual market performance or original invention of the method. Counts and numerical statements below refer to the checked-in run; refresh them if the report changes.

## Two English bullets

- Engineered a multi-asset allocation simulator comparing momentum, static allocation and two passive controls, with delayed trading, integer positions, cash financing, dividend receivables, splits and transaction costs on a synthetic market.
- Reconciled 5,040 synthetic strategy-day account records with maximum absolute NAV bridge error of 2.81e-11 currency units, and evaluated six fixed cost/delay scenarios without selecting parameters from their results.

## Evidence and restrictions

- Row counts and accounting: [daily momentum ledger](../reports/demo/momentum/ledger.csv), [metrics](../reports/demo/metrics.json), [report](../reports/demo/REPORT.md).
- Scenario evidence: [sensitivity table](../reports/demo/sensitivity.csv).
- The market is simulated; ticker names are role labels. Do not relabel synthetic Sharpe, drawdown or return as historical ETF performance, assets managed or live execution. Notional and payment-date conventions are model inputs.
- Relevant tests: future-data perturbation, no overdraft, delayed execution, split/dividend wealth preservation and independently calculated fees.
