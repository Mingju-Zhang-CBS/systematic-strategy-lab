# Intraday Data Gate

As of 2026-10-30, the public implementation is an offline execution study. The target SPY/QQQ historical evaluation is **not complete**.

| Gate | Status |
|---|---|
| Licensed access | WRDS TAQ trade and complete-NBBO queries exercised successfully |
| Cross-year pilot | Fixed ordinary, early-close and high-volatility dates checked; source records private |
| Historical schema differences | Old quote precision handled explicitly after an observed missing-field failure |
| Query equivalence | One-scan extraction agrees with the original successful pilot outputs; original timeout retained |
| Full 2016–2025 coverage | Not yet independently reconciled across every required session |
| Opening auction and trade eligibility | Pilot fields inspected; complete-history exceptions still require audit |
| Splits and distributions | Explicitly missing in extraction output until joined from a verified source |
| Cash benchmark and availability | Pending publication-aware historical join |
| Borrow and historical margin | Named proxies; actual availability not established |
| Publication rights | Raw and derived licensed results private; code license does not override data terms |

No source failure is removed merely to obtain a complete backtest. Missing corporate actions are not filled with assumed zero distributions. Current historical TAQ files may include correction processing that differs from the original real-time feed. The intended confirmation period was partly studied before, so future research must not rename it prospectively unseen.

The executable [input contract](INTRADAY_RESEARCH.md#data-interface), [verification record](INTRADAY_VERIFICATION.md), tests and synthetic report can be reviewed now. A full historical report is released only after the relevant gates pass; a smaller pilot is never relabeled as the target long-history study.
