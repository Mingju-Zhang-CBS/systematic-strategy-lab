# Intraday Momentum: Signal Time Is Not Fill Time

**Question.** Does an interpretable SPY intraday breakout retain evidence after information timing, spread, partial fills and funding are made explicit?

[Offline execution report](../reports/intraday-synthetic/REPORT.md) · [Engine](../strategy_lab/intraday/engine.py) · [Known-answer tests](../tests/test_intraday.py) · [Frozen protocol](INTRADAY_PROTOCOL.json) · [Source clocks and cash](INTRADAY_SOURCE_AUDIT.md) · [Current data gate](INTRADAY_DATA_STATUS.md)

## Evidence status

The public run is **synthetic**, not a paper replication result or trading record. Licensed WRDS TAQ source work is separate and private. The intended SPY study spans 2016–2025, with QQQ fixed as a transfer check: 2016–2019 development, 2020–2022 validation, 2023–2025 retrospective confirmation. Part of 2025 was previously studied in coursework. No refreshed split creates independently unseen evidence.

An accessible database and a successful engine test are different gates. Real evaluation requires complete trade/NBBO coverage, verified session clocks, corporate actions, publication-aware cash references, rights review and funding assumptions. Missing actions remain missing, rather than being replaced with zero dividends or unit splits. The extraction tool deliberately marks these inputs as pending. Target history is not silently shortened to produce an attractive chart.

## Economic mechanism and fixed rules

The preceding 14 full-length sessions define same-clock mean absolute opening moves. Bands anchor to the larger/smaller of today's opening price and the prior close adjusted for today's split/dividend. Prior daily total returns determine the declared volatility-scaled quantity, capped at 4x desired exposure; admission funding may permit less. Half-day sessions can trade, but are excluded from full-day band histories.

Three variants retain separate identities: opposite-band baseline, band plus cumulative trade VWAP, and the same VWAP rule with volatility sizing. Decisions occur after completed half-hour windows. Scaling is exposure management, not evidence of better information. Historical volume participation uses prior sessions, not the eventual volume of a future execution bar.

## Execution contract

1. A completed signal window produces a desired signed position.
2. Search for the first valid recorded NBBO at least 1 second later, within the following 5 seconds. A separate fixed experiment waits 60 seconds. Quotes before the request cannot fill it.
3. Buy at ask and sell at bid, adding declared per-share commissions and slippage. Size cannot exceed the displayed side in this model. Displayed quotes do not prove routeability, queue priority or actual fills.
4. Reversals consume capacity reducing old risk first; only the remaining capacity can open new risk. Funding cannot veto a valid reduction.
5. New exposure must fit the named 50% initial-margin proxy. Short availability is assumed; 6% financing and 3% borrow are scenario assumptions, not historical observations. Short proceeds remain in cash and do not create additional account equity.
6. Request flattening one minute before the supplied session close. A missed or partial exit retains shares, records provisional last-bar equity and stops that account. No zero-price exit or invented flat position is inserted.

Borrow and financing accrue over elapsed seconds. Both sides of a reversal pay costs. Complete days reconcile signed trade cash flows, costs and financing to final cash. No intrabar high/low is used to invent stop sequencing.

## Data interface

`python -m strategy_lab.intraday --demo --output output/intraday` runs offline. For authorized private inputs, use `--bars bars.csv --quotes quotes.csv --output /private/output`.

Bars contain `asset, bar_end, session_open, session_close, close, volume, dollar_volume, open_price, cash_dividend, split`. Timestamps have explicit zones and normalize to UTC. The input must contain every expected half-hour window for each supplied session; incomplete days require explicit upstream quarantine. Quote fields are `asset, quote_time, bid, ask, bid_size, ask_size, condition`. Sizes are shares. Nonregular, nonpositive or crossed quotes are retained as invalid inputs and cannot fill an order. Conflicting same-time quotes require quarantine rather than an arbitrary order assumption.

Only K-line data cannot support this quote-backed contract. A future bar-only comparison must have its own label and next-minute price/cost assumptions. It is not currently substituted for the main study.

## Source engineering

The [WRDS extraction tool](../tools/extract_wrds_intraday.py) uses consolidated trades and complete NBBO, with explicit supplied session calendars. Regular and intermarket-sweep trades drive price endpoints; odd lots can contribute to transaction VWAP. Opening auction records are identified separately on the primary listing venue. Unknown auctions, ambiguous quotes, remote failures and incomplete corporate actions remain in receipts. These current-vintage processed daily files are not archived original SIP message histories; correction processing can itself differ from a historical real-time feed.

Use a dated calendar exported from `exchange_calendars` 4.13.2 and preserve its fingerprint. It is a current historical schedule, not evidence of original exchange publications or every unexpected closure. WRDS Cloud may have no outbound network; calendar construction can run locally without installing anything on its shared runtime.

## What is deliberately not claimed

Course results are not transferred into this implementation. A profitable simulated path is not an executed strategy; a losing path is retained. Corporate-action, cash-benchmark and historical borrow gaps block a full real-data validation claim. Public charts use invented inputs; licensed prices, quotes, source-derived figures and reports remain private unless their publication rights are established.

Research direction: Mingju Zhang. Code and documentation were independently reconstructed with AI assistance, using public methodology rather than copying group submissions or author code. Source learning included Zarattini, Aziz and Barbon's [intraday momentum paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172), reviewed critically. [NYSE TAQ specifications](https://www.nyse.com/publicdocs/nyse/data/Daily_TAQ_Client_Spec_v4.0.pdf) define trade and quote fields. Neither source establishes profitability for this implementation.
