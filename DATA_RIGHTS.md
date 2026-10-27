# Data rights, attribution and scope

## Commodity module: separate evidence and rights

The [commodity module](docs/COMMODITY_ACCOUNTING.md) publishes original code,
current public contract-unit facts with exchange citations, and generated
**synthetic** prices, calendars, contracts, results and figures. Its fixture
identities and expiry dates are invented. The code license does not license CME
market data or imply a historical exchange-calendar/specification archive.

WRDS/LSEG Datastream observations, vendor metadata extracts, private audit
tables and reconstructible real-price figures are **not included**. No grant
to redistribute licensed records or derived findings is inferred from a WRDS
subscription, `licflag`, a successful query, or aggregation. The
[WRDS download policy](https://wrds-www.wharton.upenn.edu/pages/about/data-download-and-analysis-policy/)
requires respecting the applicable vendor agreement and private storage/retention
obligations. Real input bundles and their generated outputs must remain private
until their particular rights are established. The TSP factual-data basis below
does not apply to those licensed futures records.

## Published snapshot

`strategy_lab/data/tsp_nav.csv` contains **numerical daily fund share-value facts**, transcribed from the official [Thrift Savings Plan share-price history](https://www.tsp.gov/share-price-history/): Individual funds → All Time → visible data table. Attribution: Federal Retirement Thrift Investment Board / Thrift Savings Plan. Capture date, original table fingerprint, normalized CSV fingerprint and date coverage are recorded in [source.json](strategy_lab/data/source.json). Only dates and G/F/C/S/I numerical values are included; the study ends on 31 December 2025.

The rights basis is **public factual data and U.S. government works**, rather than a Creative Commons license invented for TSP. The [FRTIB open-data plan](https://www.frtib.gov/pdf/data/Open_Data_Plan_v4.0.pdf) identifies fund share-price data for public download and machine-readable publication; its [official catalog](https://www.frtib.gov/data.json) lists Share Price Data as public. A catalog access flag is evidence of public availability, not a copyright license by itself.

The [U.S. Copyright Office](https://www.copyright.gov/help/faq/faq-protect.html) explains that facts are not protected by copyright; [17 U.S.C. §§102(b) and 105](https://www.copyright.gov/title17/92chap1.html) address subject-matter exclusions and U.S. government works. This repository redistributes the numerical facts in an independently written CSV, not creative website content or a proprietary index database. It makes no blanket public-domain assertion about everything hosted on tsp.gov or about third-party works. It does not claim a worldwide Creative Commons grant from FRTIB.

## What is and is not included

- Included: dates and five fund NAV facts; original research code, explanatory writing and figures.
- Not included: source website HTML, branding, agency seals, full brochures, auditor prose, licensed benchmark levels, constituent files, commercial ETF data or employer materials.
- Original code and authored documentation: [MIT](LICENSE). The code license does not relicense third-party materials, trademarks or data over which the author has no rights.

The U.S. government and TSP do not sponsor or endorse this project. Fund names are identifiers. These are restricted-access retirement-plan fund units; public access to historical values does not imply public eligibility to invest.

## Economic meaning and vintage

Fund investment income, including dividends and interest, is reflected in share value; operating expenses are embedded. The [TSP financial statements, Note 2](https://www.frtib.gov/pdf/reading-room/FinStmts/TSP-FS-Dec2023.pdf) explain investment-income recognition and expenses. No separate dividend or expense is added to this series. Underlying security prices and ex/pay-date cash flows cannot be reconstructed from fund NAV alone.

This is an October 2026 capture of published historical values. It is not an archive of historical releases. No exact historical publication timestamps or revision log accompany it. A conservative lag is modeled and sensitivity-tested; that does not repair unknown past revisions. The I Fund's investment benchmark changed during 2024: see the [FRTIB announcement](https://www.frtib.gov/pdf/reading-room/PressRel/PR_2023-11-14_I-Fund-Benchmark-Change.pdf). No constant-benchmark history is implied.

## Refreshing data

The checked-in snapshot makes offline reproduction possible without services, credentials or a downloader that depends on site internals. To propose an update, retrieve the official table through its public interface, preserve a private source capture, normalize exactly the six columns, document rights and meaning, and create a new source fingerprint and protocol version before evaluating a new horizon. Do not overwrite the snapshot and continue citing the old results. The website's current interface and data availability can change.
