# Intraday Data Gate

As of 2026-10-31 UTC, the public implementation is an offline execution and data-validation study. The target SPY/QQQ historical evaluation is **not complete**. Private prefix ledgers are diagnostics and do not replace that target.

| Gate | Status |
|---|---|
| Licensed access | WRDS TAQ trade and complete-NBBO queries exercised successfully |
| Cross-year pilot | Fixed ordinary, early-close and high-volatility dates checked; source records private |
| Historical schema differences | Old quote precision handled explicitly after an observed missing-field failure |
| Nanosecond/order adjudication | NBBO/CQM origin, dated self-NBBO indicator, exact lot identity and nanosecond checks; unproven matches stay quarantined |
| Query equivalence | One-scan extraction agrees with the original successful pilot outputs; original timeout retained |
| Full 2016–2025 coverage | Not yet independently reconciled across every required session |
| Opening auction and trade eligibility | Pilot fields inspected; complete-history exceptions still require audit |
| Splits and distributions | Full target-period current-vintage source obtained; amounts and units cross-checked; missing/same-day declaration clocks remain unavailable |
| Primary publication evidence | Selected 2025 QQQ amounts linked to official exchange release listings; minute precision uses conservative upper bounds; earlier gaps remain |
| Cash benchmark and availability | Separate current-vintage EFFR opportunity-cost proxy; primary scheduled 14:45 ET availability and retained 09:15 sensitivity; not archived release timestamps |
| Borrow and historical margin | Named proxies; actual availability not established |
| Publication rights | Raw and derived licensed results private; code license does not override data terms |

No source failure is removed merely to obtain a complete backtest. Missing corporate actions are not filled with assumed zero distributions. Current historical TAQ files may include correction processing that differs from the original real-time feed. The intended confirmation period was partly studied before, so future research must not rename it prospectively unseen.

[Evidence adjudication](INTRADAY_EVIDENCE.md) preserves source corrections and the original failure baseline separately. Software support for a precise publication clock does not imply that every historical event has that evidence. An alternate current-vintage declaration date, when available and matched, retains the original dated-proxy label.

The [source-audit methods](INTRADAY_SOURCE_AUDIT.md), [invented clock/action examples](../reports/intraday-data-fixture/REPORT.md), executable [input contract](INTRADAY_RESEARCH.md#data-interface), [verification record](INTRADAY_VERIFICATION.md) and tests can be reviewed now. Same-time quote conflicts, possible delayed opening evidence and failed/partial closing orders remain distinct diagnostics. Current-vintage numerical reconciliation is not proof of historical publication timing. A full historical report is released only after the relevant gates pass; a smaller prefix is never relabeled as the target long-history study.

An alternate current-vintage declaration date is assessed separately from primary publication evidence. Exact identity/amount matching stays frozen; missing dates and precision mismatches remain unresolved. A later proxy cannot unlock the first earlier source blocker or restart a stopped account. See [the two evidence lanes](INTRADAY_EVIDENCE.md#a-declaration-date-is-a-different-kind-of-evidence).
