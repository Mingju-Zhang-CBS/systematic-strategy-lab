# Allocation study: source, contribution and data boundaries

## Reference and independent work

The user supplied a [public Drive collection](https://drive.google.com/drive/folders/1Buag4I1uqeiFbAN9Gtxy25lHNK5-oheB),
including `Markowitz vs black litter man.ipynb` and `Risk parity vs relaxed risk.ipynb`.
They motivated the comparison of return-driven and risk-driven construction.
The inspected notebooks did not provide an identifiable author or explicit
redistribution license. No reuse rights or ownership are inferred. Reference
fingerprints and the source review remain private.

This module independently implements the mathematical models, labelled views,
convex risk-budget objectives, numerical acceptance diagnostics, chronological
estimation, funded account, controlled shocks, inference, tests and explanatory
writing. Notebook code, saved figures, results and prose are excluded. Mingju
Zhang selected the research direction; implementation, experiments and writing
were AI-assisted. Familiar models are not claimed as novel; personal understanding
requires human review beyond successful automated tests.

The return-tilted risk-budget objective is explicitly defined in this project.
It is RRP-inspired, not claimed as a replication of a uniquely specified canonical
relaxed-risk-parity paper. The equal-weight-reference BL prior is a modelling
assumption, not observed historical market capitalization. The common account
and existing paired-block inference helper are acknowledged project components.

## Primary method/software references

- [Black–Litterman method documentation](https://pyportfolioopt.readthedocs.io/en/latest/BlackLitterman.html):
  prior, named picking matrix, view uncertainty and posterior mean/covariance.
  This implementation uses independent linear solves, not PyPortfolioOpt code.
- [Ledoit–Wolf estimator documentation](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html):
  scikit-learn's upstream shrinkage estimator; dependency version is fixed at 1.5.2.
- [SciPy SLSQP documentation](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html):
  solver interface and convergence flags; dependency version is fixed at 1.14.1.
  Additional project acceptance checks do not rely on newer-version multiplier fields.
- [yfinance documentation](https://ranaroussi.github.io/yfinance/): an unofficial
  research/education client, whose data-use guidance directs users to Yahoo terms
  and identifies the API as intended for personal use.
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars): current
  XNYS historical sessions, not an archive of original exchange publication times.

NumPy, pandas, SciPy, scikit-learn, threadpoolctl, Matplotlib and the other locked
dependencies retain their authorship and licenses. MIT covers original project
code, not third-party references, vendor data or trademarks.

## Public and private evidence

`reports/allocation-synthetic/` contains only results generated from independently
invented factor-driven price paths. SPY/EFA/IEF/GLD/DBC are fixture roles. The
invented dates include business days that would be exchange holidays; the fixture
does not claim to reproduce actual ETF history, tradability or market calibration.

Personal real-reference work requests full 2009–2025 adjusted closes through
yfinance. Provider responses, normalized prices, session calendars, source
receipts, real ledgers, model parameters, figures and performance summaries stay
outside the public repository. Public accessibility, a successful download or a
software license does not establish rights to redistribute those artifacts.
The TSP factual-data basis used elsewhere in this repository does not apply to
Yahoo ETF history. No dissemination permission is inferred from the reference
author sharing a notebook.

Yahoo adjustment history is today's vintage. A delayed order does not recover
original release versions or historical corporate-action information. Model
total-return units cannot establish ETF share accounting or executable fills.
Any wider dissemination requires a documented basis for that particular data
source and artifact. No employer, original coursework or recruiting-task code
is included. Real results are not silently replaced by a synthetic chart when
data retrieval fails; the failure receipt and requested horizon are retained.
