# Sources, contribution and limits

This independent public implementation was written from public financial concepts. Prior academic or professional interests motivated the questions; original coursework, internship workbooks, recruiting tasks, internal APIs and employer data are not copied into this repository. No official trading-competition result is claimed for this study. Development and documentation were AI-assisted.

## Data and permissions

- [TSP official share-price history](https://www.tsp.gov/share-price-history/): numerical daily G/F/C/S/I fund NAV facts, captured via its public Individual funds / All Time table. The October 2026 capture is truncated at 31 December 2025 before the experiment.
- [FRTIB data catalog](https://www.frtib.gov/data.json) and [open-data plan](https://www.frtib.gov/pdf/data/Open_Data_Plan_v4.0.pdf): public machine-readable share-price data. Public access flags alone are not treated as copyright licenses.
- [Data rights](../DATA_RIGHTS.md): public-fact and U.S.-government-work basis, source fingerprints, attribution, exclusions and licensing scope. No third-party benchmark levels, site HTML, government marks or brochures are redistributed.
- [TSP financial statements, Note 2](https://www.frtib.gov/pdf/reading-room/FinStmts/TSP-FS-Dec2023.pdf): income recognition and embedded expenses. The original numerical series is not relabeled as unadjusted ETF closes.
- [5 CFR Chapter VI, 2024 edition](https://www.govinfo.gov/content/pkg/CFR-2024-title5-vol3/pdf/CFR-2024-title5-vol3-chapVI.pdf), §§1601.22/1601.32: whole-percent reallocations, ordinary processing cutoff and monthly transfer limits. Rules guide a simplified model, not a complete participant implementation.
- [I Fund benchmark change announcement](https://www.frtib.gov/pdf/reading-room/PressRel/PR_2023-11-14_I-Fund-Benchmark-Change.pdf): the 2024 mandate transition. The series is the realized changing fund rather than a stationary index history.

The model's 11:00 request, publication allowance, proportional friction, risk thresholds and initial balance are research assumptions. They are not official TSP specifications, observed fills or measured fees. Sources do not validate this strategy's predictive value.

## Personal implementation

I designed and implemented the offline snapshot schema, timing contract, capped momentum and shared-risk-budget control, self-financing fee solver, unit/P&L ledger, chronological experiment, paired inference, figures and validation tests. Python, NumPy, pandas, Matplotlib, psutil and pytest provide their respective libraries. Familiar momentum and covariance methods are public building blocks; no claim of a novel signal is made.

## Remaining uncertainty

Historical release vintages and exact publication clocks are unavailable. A full-session delay is a conservative assumption, not a complete point-in-time guarantee. There is no independent future trading record. Fund eligibility, taxes, external contributions, unit rounding, administrative errors, exceptional posting delays and exchange capacity are outside scope. G is not an ordinary listed cash substitute. The confirmation momentum advantage is unproven, and unfavorable results are retained.

The [legacy synthetic report](../reports/demo/REPORT.md) and its split/payment examples remain explicitly synthetic. Their results and ticker labels are not transferred to the real-data study.
