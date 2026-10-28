# Standardized futures input contract

`python -m strategy_lab.commodities --input PRIVATE_FOLDER --protocol protocol.json --output PRIVATE_NEW_FOLDER`

The input directory is private by default. Validate once at the CLI boundary;
schema errors fail explicitly, economic exclusions and failed executions are
logged. There is no automatic website downloader, credential handler or database
dependency in this package. Raw vendor tables are **not** ready for this command.

## Files

**`manifest.json`**: `data_kind` (`synthetic`, `restricted`, or `public`), `rights`,
`source`, `calendar_basis`, `start`, `end`. Include extraction/version and evidence
references in additional fields. Public availability is not redistribution
permission. A restricted run and all its output stay private.

**`quotes.csv`**: `contract`, `session` (local exchange session date), `settlement`
(raw vendor quote units), `volume`, `open_interest`, `available_at` (offset-bearing
timestamp). Missing economic values are allowed and recorded as exclusions or
stale/fill failures. Infinity, negative volume/OI and ambiguous duplicate
contract/session/availability keys are errors. Negative settlements are valid.
Versions with different availability timestamps are supported. Later versions
enter decisions only after availability; the last supplied version defines
retrospective marking. Supply the assumed t+1-end availability explicitly when
historical release stamps are unavailable, and disclose this assumption.

**`contracts.csv`**, one row per version:

|Columns|Meaning|
|---|---|
|`contract`, `product`, `delivery`|Stable economic identity and maturity; product is one of the eight documented identifiers|
|`listed_at`, `known_at`|When the contract was listed and this metadata version was known; explicit UTC offsets|
|`valid_from`, `valid_to`|Inclusive dates for this specification version|
|`first_notice`, `last_trade`, `first_position`|Documented delivery-risk dates; first position may be blank if upstream evidence rules it inapplicable|
|`multiplier`, `usd_scale`, `outright_tick`|Physical size, USD per raw quoted unit, outright tick in USD per physical unit|
|`boundary_verified`, `listing_verified`, `spec_verified`|Explicit booleans asserting documentary checks for the historical scope|
|`source`|Evidence identifier/URL, with dated private evidence in a restricted study|

Notice and last trade are required for qualification. Missing evidence is not
repaired from today's rulebook or a vendor start-of-data date. Known overlapping
versions use latest `valid_from`, then latest `known_at`; this is an explicit
version-precedence rule, not a forward lookup. A held contract whose evidence
expires or whose physical units change stops with an evidence failure rather
than being silently reinterpreted. Future known-at versions cannot alter past
selection. Two distinct eligible IDs with the same product/maturity quarantine
the product's new pair.

**`calendar.csv`**: `product`, `session`, `decision_at`, `settlement_at`, `known_at`,
`verified`, `source`. Unique product/session keys. Include prehistory for lag/risk
calculations and sessions through every potential delivery boundary. Daily
decisions share one UTC timestamp across open products and precede each local
settlement. A supplied calendar must be complete for the scope being certified;
the validator cannot discover omitted exchange holidays or missing sessions.
Flag unverified calendars false. Weekdays or observed quote-date unions are
illustrations, never certified exchange history. The exact session conventions
and historic holiday changes belong in upstream evidence.

## Protocol and research stage

An optional JSON object overrides named `Protocol` dataclass fields. The full
effective configuration and its hash are saved. Defaults: $1m, one paired unit,
five-session exit, $2.50/side, one outright tick, 1% lagged-volume capacity,
OI≥100, 10% model reserve, 50% reserve/equity, 3× gross, 10% forecast risk,
252 risk days/minimum126 and a 60-price median window. Reusing a modified
configuration creates another scenario; it does not become a new confirmation
test without a separately frozen research protocol.

This interface implements fixed pair requests and constraints for stage 2.
The separate [monthly signal interface](COMMODITY_SIGNALS.md) computes
carry/trend/BM directions from supplied monthly rolling returns and curve
snapshots. It does not change this CLI into a historical strategy study.
The [separate exploratory runner](COMMODITY_RESEARCH.md) now provides a
current-vintage snapshot adapter, same-contract reference ladder, integer risk
allocation and paired inference under a declared scheduled-calendar assumption.
This does not certify complete PIT history, first-position boundaries, actual
margin feeds or executable fills. The original stage-2 CLI retains its fixed
accounting-diagnostic scope.
