# Interview discussion guide

## Two-minute explanation

This is an independent, AI-assisted account simulator for comparing a fixed momentum rule with static and passive controls. The public example uses a synthetic five-asset market. I focused on when a signal becomes available, how trades consume cash, and how NAV changes through fees, splits and dividend receivables. Each daily account row reconciles to an explicit P&L identity. The example is about implementation and economic conventions, not evidence of profitable historical alpha.

## Questions to be ready to answer

1. **When is the signal tradable?** A decision uses data through a close, with a 21-observation skip in the momentum component. It becomes eligible for execution at a later close. The execution model sizes integer shares using then-observed NAV and prices; daily bars do not establish attainable fills.
2. **Why are dividends receivables?** A stock loses the entitlement at the ex-date, but the investor receives cash later. Accrual preserves economic NAV; delaying payment prevents spending cash before it is available. Payment itself does not create profit.
3. **What is the accounting identity?** Ending NAV equals prior NAV plus price P&L, dividend entitlement and cash interest, less trading fees. NAV is cash plus receivables plus marked holdings. Read a small numerical ledger example directly.
4. **Why sell before buying?** A long-only cash account cannot spend sales proceeds before modeling the sale. Purchases are scaled to available cash including fees; receivables cannot fund them.
5. **How do splits enter?** Quantity is multiplied by the split ratio. Raw price changes, post-split dividends and changed share counts are reconciled; adjusted prices must not be combined with separate adjustment events.
6. **What are the controls?** Static uses equal target weights without volatility scaling. SPY/QQQ enter once and hold. They share the account period and cash/dividend conventions, but have different exposures; return differences are not pure signal skill.
7. **How is Sharpe defined?** Daily account return minus the same period's cash return, mean divided by standard deviation and scaled by sqrt(252). The sampling and independence assumptions are limitations.
8. **What do caps guarantee?** Target weights satisfy caps on decision dates. Realized weights can drift afterward. The demo does not promise a continuously enforced risk limit or executable capacity.
9. **What failure did tests target?** Changing only future prices must leave past decisions and ledgers unchanged. Split/dividend examples must preserve wealth, and transaction costs must reduce a passive account's terminal NAV on identical inputs.
10. **What would come next?** Permission-cleared market data, real calendars/payment dates, quoted bid/ask and financing, capacity checks and a prospectively fixed validation period. None should be silently inferred from this synthetic study.

## Suggested live demonstration

Open a decision and its later filled order, then reconcile the corresponding daily NAV. Show the split-plus-dividend test and cost/delay plot. Explain why a strong-looking synthetic curve cannot be used as a market-performance claim.
