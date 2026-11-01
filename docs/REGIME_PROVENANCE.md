# Regime research: sources, contribution and data boundaries

## Reference and independent contribution

The user supplied a [public Drive collection](https://drive.google.com/drive/folders/1Buag4I1uqeiFbAN9Gtxy25lHNK5-oheB)
containing `HMM momentum.ipynb`, `HMM market regime.ipynb`, and two portfolio
optimization notebooks. The HMM notebooks motivated the question of combining
trend, smoothing, volatility and hidden states. The supplied folder did not
provide an identifiable author or an explicit code redistribution license in
the inspected notebook content. No authorship or reuse license is inferred.
Reference-file fingerprints and the initial source review are retained privately.

This module is an independently written, AI-assisted implementation of familiar
methods. It does not copy notebook source, saved outputs, figures, performance
numbers or wording. Mingju Zhang chose the direction, asset universe and long-only
scope. New work includes the forward filter, training boundaries and snapshots,
matched EMA comparison, next-close funded total-return-unit engine, failure
policy, fixed experiment, paired inference, tests and explanatory writing.
Implementation assistance does not establish personal mastery; human review and
understanding remain separate from automated verification. No novel HMM or
Kalman mathematics, live trades or verified alpha is claimed.

## Method and software references

- [hmmlearn API](https://hmmlearn.readthedocs.io/en/stable/api.html): Gaussian HMM
  parameters, EM monitoring, decoding and posterior interfaces. Evaluation
  probabilities use our forward recursion, not whole-sequence decoding.
- [hmmlearn source](https://github.com/hmmlearn/hmmlearn): upstream implementation
  retains its own license and attribution.
- [yfinance documentation](https://ranaroussi.github.io/yfinance/): the downloader
  is an unofficial research/education client. Its documentation identifies Yahoo
  data as intended for personal use and directs users to provider terms.
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars): current
  XNYS historical session schedule, not an archive of original exchange notices.
- NumPy, pandas, SciPy, scikit-learn, joblib, threadpoolctl and Matplotlib retain
  their authorship and package licenses. Original project code follows this
  repository's MIT license; that license does not relicense data or references.

## Public demonstration versus real reference work

All numerical results and figures in `reports/regimes-synthetic/` are generated
from the independently invented fixture. Its prices, hidden regimes and
business-day dates do not reproduce actual ETF history or trading calendars.
The synthetic transition process is not a market calibration and the HMM is not
given the generator's hidden states. Invented results test the research workflow,
not real financial performance or estimator correctness by themselves.

Personal real-reference work requests SPY and QQQ adjusted closes for 2009–2025
through yfinance. Both normalized and provider responses, calendar, capture time,
dependency versions, fingerprints and failure receipts are stored outside the
public repository. Adjusted history is today's vintage; historical revision,
corporate-action availability and original publication clocks are not recovered.
Adjustment factors are not observed trade prices. This is not the repository's
TAQ execution model, and it makes no quote, liquidity or actual-fill claim.

Public access and a successful download do not establish permission to publish
provider prices or reconstructible derived figures. The first release keeps
real inputs, figures, ledgers and derived result summaries private. Further
dissemination needs a documented basis for the particular source and artifacts.
No blanket permission is inferred from the original poster sharing notebooks,
Yahoo access, a university subscription or an MIT software license.

The TSP snapshot's factual-data basis elsewhere in this repository does not
extend to Yahoo ETF observations. No employer, coursework or recruiting-task
source code is added by this module.
