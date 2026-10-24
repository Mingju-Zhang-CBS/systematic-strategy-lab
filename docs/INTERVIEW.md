# Interview guide: investment evidence meets implementation

## A 90-second explanation

“I wanted to test whether a momentum filter adds value once it sits inside a funded multi-asset allocation. I used official public fund NAVs with a documented factual-data rights basis, then treated NAV income, publication timing and posting as separate contracts. Momentum and static share the risk-budget procedure. I froze the rule before calculating this implementation's results and kept chronological windows and nine execution/cost stresses. The 2020–2025 confirmation difference is negative and its block interval includes zero. The useful outcome is an auditable research system and an honest comparison, not a claim of discovered alpha.”

## Questions to be ready for

1. **Why these instruments?** Clear public numerical facts and diversified stock/bond/reserve exposures. TSP units have eligibility and transfer constraints; they are not a direct replication of an ETF portfolio. G has a special mandate, and the I mandate changed in 2024.
2. **What does NAV mean for dividends?** Income and operating expenses are embedded; adding another dividend or cash yield would overstate wealth. The synthetic raw-price example teaches the separate ex/pay-date case.
3. **Where can leakage remain?** Features are trailing and requests precede posting prices, but current-vintage historical revisions and missing historical publication times remain limitations. A delay is not a vintage archive.
4. **Is the static control truly risk matched?** It shares caps, covariance scaling and volatility budget. Realized volatility can differ, particularly when the filter selects different funds or the volatility target is not binding.
5. **How are costs funded?** Solve after-fee portfolio value and fee jointly; both the sold reserve and bought fund count toward gross notional. Reconcile each daily bridge and transfer.
6. **What is out of sample here?** Temporal historical confirmation with no confirmation-driven rule selection, not a prospective independent market record. Familiar market episodes cannot be made unseen by a new split.
7. **What failed?** Momentum underperformed the static control in confirmation and all nine predefined stress comparisons; uncertainty remains material. Do not tune the filter against that window and relabel it untouched.
8. **What would you do next?** Register a new forward evaluation, obtain archived NAV publication vintages if available, and extend to a licensed exchange-instrument dataset with actual corporate actions, quote timing and executable constraints.

For an investment role emphasize opportunity cost and allocation robustness. For data science emphasize source quality, temporal alignment and uncertainty. For markets and portfolio solutions emphasize valuation versus posting, funding and explaining a product's operational limits.
