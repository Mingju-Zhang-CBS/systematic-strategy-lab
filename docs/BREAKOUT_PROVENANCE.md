# Breakout transfer: source, contribution and rights

The user-supplied [Drive collection](https://drive.google.com/drive/folders/1Buag4I1uqeiFbAN9Gtxy25lHNK5-oheB)
and its `HMM market regime.ipynb` motivated project ④. The notebook is a
conceptual reference, not repository source. Its inspected approach used
different state features/training, pulse breakout semantics and leverage/shorting.
Our primary persistent long/cash channel and frozen parent 756/21 two-feature
HMM are explicit independent design decisions. Pulse55 is retained as a
predeclared semantic sensitivity. No unused ATR indicator is presented as risk
sizing. Source-review fingerprints remain private.

No identifiable author or express redistribution license was established in
the inspected reference content. Sharing a notebook does not grant reuse rights.
No notebook code, outputs, figures, performance statistics or prose is copied.
Mingju Zhang chose the research direction and private/public boundary;
implementation, tests and writing are independently produced with AI assistance.
Automated checks do not establish unaided personal mastery or novel mathematics.

The [parent contribution record](REGIME_PROVENANCE.md) documents the independently
written forward filter and funded account engine reused here. New contributions
are prior-bar OHLC channels with explicit latches, a fixed two-by-two experiment,
frozen-parent binding/equivalence checks, same-vintage OHLC preparation,
paired interaction analysis, independent trade reconstruction and learning notes.

The [hmmlearn 0.3.3 API](https://hmmlearn.readthedocs.io/en/stable/api.html)
distinguishes complete-sequence decoding/smoothing from filtering. We fit its
Gaussian HMM, retain the parent's stricter training checks, and independently
advance probabilities with the parent's forward recursion. No complete-sequence
decoding is used to relabel evaluation signals.

The [yfinance documentation](https://ranaroussi.github.io/yfinance/) identifies
the client as unofficial and directs users to Yahoo's data-use terms. Public
access is not a dissemination license. Existing captured real provider OHLC,
adjusted bars, fitted models, ledgers, reports and all derived real findings
remain outside both public repositories. The software MIT license does not
relicense source notebooks, Yahoo observations or third-party dependencies.

Public `reports/breakout-synthetic` contains independently invented parent
closes and independent invented open/high/low envelopes. Its ticker names are
role labels and its business-day dates include actual market holidays. Nothing
in its figures or snapshots reconstructs actual ETF observations or establishes
market calibration. Library authorship and licenses remain with their authors.
