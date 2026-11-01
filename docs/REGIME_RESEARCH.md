# Online market regimes: does the extra model earn its complexity?

The question is whether a causal HMM adds value beyond ordinary trend, smoothing
and volatility control. SPY is the primary study; QQQ is a fixed-rule transfer
check. This is a daily study, separate from the repository's intraday breakout
and fund-NAV allocation studies. This parent release covers momentum; the
[breakout transfer experiment](BREAKOUT_RESEARCH.md) now keeps this HMM fixed
while testing prior-high/low channels with and without volatility sizing.

[Invented results](../reports/regimes-synthetic/REPORT.md) ·
[Frozen protocol](REGIME_PROTOCOL.json) · [Tests](../tests/test_regimes.py) · [Validation](REGIME_VALIDATION.md) ·
[Chinese learning notes](REGIME_LEARNING_CN.md) · [Source and data rights](REGIME_PROVENANCE.md)

## Six methods with common dates

| Method | Desired risky fraction after close t |
|---|---|
| Buy and hold | Request 100% once, then retain the purchased model units |
| Volatility-controlled holding | `min(1, 0.15 / sigma_t)` |
| Raw momentum | Same risk fraction if the 20-session log-index change is positive; otherwise zero |
| EMA momentum | Same rule using the matched-gain EMA log index |
| Kalman momentum | Same rule using the Kalman-filtered log index |
| Kalman + HMM | Kalman rule, additionally requiring the filtered state-weighted log-return mean to be positive |

`sigma_t` is the sample standard deviation of the last 20 daily log returns,
annualized by sqrt(252). A zero volatility estimate requests zero exposure.
The cap is 100%; lower risk and time in cash may explain differences in results.
These rules do not guarantee 15% realized volatility. Buy and hold is an
opportunity-cost reference, not a risk-matched control. The direct incremental
comparison is Kalman + HMM minus Kalman, using the same risk-scaling procedure.

## Smoothing: Kalman versus an honest EMA control

Let `x_t = log(adjusted_close_t / adjusted_close_0)`. Use the scalar random-walk
state and observation model with Q=0.00001, R=0.001. Initialize the filtered
level at x_0 and posterior variance at 1. The one-step update is:

```text
P_pred = P_previous + Q
K = P_pred / (P_pred + R)
filtered = filtered_previous + K * (x_t - filtered_previous)
P = (1 - K) * P_pred
```

The positive steady-state posterior variance is
`P_inf = (sqrt(Q² + 4QR) - Q) / 2`; the matched EMA coefficient is
`alpha = (P_inf + Q) / (P_inf + Q + R)` (approximately 0.095125).
Initialize the EMA at the same first observation. Kalman and EMA should become
extremely similar after warmup. This is a useful negative control: a constant
variance Kalman filter is not automatically a new source of market information.
All momentum decisions use a 20-session difference of the corresponding level.

## HMM estimation and online inference

Features are current daily log return and trailing annualized volatility. Fit a
three-state diagonal-covariance Gaussian HMM on the previous 756 complete
feature observations, excluding today's observation. Refit every 21 sessions,
anchored to the first evaluation date. Standardize using only the training
window's mean and population standard deviation. Fix seed 42, at most 500 EM
iterations, tolerance 0.001 and the library covariance floor parameter 0.0001.
Thread pools are limited to one during fitting.

A fit is accepted only with finite likelihood history and last likelihood gain
in [-0.001, 0.001). A materially decreasing likelihood, unconverged iteration
limit, degenerate feature, invalid covariance/probability, or numerical error
requests cash until the next scheduled refit. Warning text, iterations and
failure reasons are retained. Unsupported programming errors propagate; they
are not silently converted into favorable observations.

On refit, sort states by their fitted emission means in original daily log-return
units, for readable parameter snapshots. Names are low/middle/high conditional
return; they do not establish economic bull/bear regimes or next-day forecasts.
Re-filter the entire training window under the newly fitted parameters to
initialize the current distribution. Within each model's life, carry the
distribution forward:

```text
prior_t[j] = sum_i(filtered_probability_previous[i] * transition[i,j])
filtered_probability_t[j] proportional to prior_t[j] * emission_density_j(z_t)
regime_score_t = sum_j(filtered_probability_t[j] * fitted_log_return_mean[j])
```

The initial training observation uses the fitted starting distribution without
an extra transition. Log-domain normalization avoids likelihood underflow.
An entire history is never retrospectively rewritten after later observations.
One-row `predict` and whole-sample Viterbi/smoothing are not used for trading
states. Fitting with historical smoothing inside a completed training window
does not permit using future observations when computing an evaluation signal.

The regime score describes the filtered current state. It is not a calibrated
expected next-day return. Signals require both positive Kalman momentum and a
positive score; failed models request zero, with the ordinary execution delay.

## Observation, execution and a funded account

The source is an adjusted-close total-return reference. We model fractional
total-return units, not observed ETF shares or attainable adjusted-price fills.
No separate dividend is added. After close t the target fraction is frozen;
the modeled rebalance occurs at close t+1, using then-current pretrade equity.
Old units earn the intervening price move. New units earn returns only after
execution. The first evaluation session begins with cash for every method.
Buy and hold places only its initial request. Other rules request their fraction
daily, including the resulting trades to correct market-induced weight drift.

With pretrade risky value A, total equity V, target w, fee rate c and signed
traded notional d, solve funding exactly:

```text
d = (w*V - A) / (1 + w*c)     for buys
d = (w*V - A) / (1 - w*c)     for sells
fee = c * abs(d)
cash_after = cash_before - d - fee
units_after = units_before + d / execution_model_price
```

The target is a fraction of after-fee equity. There is no external capital,
short position or borrowing. Check each day's equity bridge and independently
reconstruct final cash and units from trades. The last unexecuted request is
recorded; no terminal liquidation or fictitious liquidation fee is inserted.

Cash earns continuously compounded 0% in the base case, with 3% as a separate
assumption sensitivity, accrued over actual calendar days/365.25. These are not
historical deposit or Treasury rates. Costs are 0/5/10 bp per dollar traded,
including first entry and reductions; they are scenarios, not measured spreads.

## Evaluation and interpretation

Capture 2009–2025, evaluate common sessions in 2013–2025. Development is
2013–2017, validation 2018–2020 and historical confirmation 2021–2025. Holdings,
cash and rolling estimation continue across boundaries. No setting is selected
from these windows; their familiar history does not become independently unseen
evidence. QQQ receives exactly the same rules and is not an independent asset
class. Missing input dates block real evaluation rather than shortening history.

Report every asset × six methods × three costs × two cash assumptions × four
periods (288 metric rows). Show CAGR, arithmetic-excess-return annualized Sharpe,
realized volatility, drawdown including initial wealth, annual turnover, average
held/end exposure, fees, minimum cash and reconciliation residuals. Training
failure counts are reported separately, by asset and period.

For each scenario/period, bootstrap the aligned daily arithmetic-return difference
between HMM and Kalman using noncircular moving blocks of 20 and 63 sessions,
2,000 resamples and seed 42. The final block is truncated to the original sample
length. Annualize the mean by 252 and report percentile 95% intervals and the
average held-exposure difference (96 paired rows). These are descriptive
dependent-data diagnostics, without multiple-comparison adjustment. A positive
estimate does not by itself demonstrate predictive alpha, or separate regime
information from spending more time in cash. Insignificant and adverse outcomes
remain in the report.

## Reproduce

Python 3.12, CPU only. From the repository root:

```bash
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest tests/test_regimes.py
python -m strategy_lab.regimes --demo --output local-runs/regimes
```

The deterministic invented fixture covers business days, including dates that
would be actual exchange holidays; these are explicitly invented sessions.
SPY/QQQ are role labels in that fixture, not actual ETF prices. No network,
credentials or paid service is required for the demo. Use a new output directory.

For a personal real-data capture, install the optional downloader dependencies
and choose an absolute output directory outside the public repository:

```bash
python -m pip install '.[regimes-download]'
python tools/download_regime_prices.py --output /private/regime-capture
python -m strategy_lab.regimes --prices /private/regime-capture/prices.csv --sessions /private/regime-capture/sessions.csv --source /private/regime-capture/source.json --output /private/regime-study
```

The input CSV has exactly `date,ticker,adjusted_close`, ordered by date and ticker,
unique positive finite observations, and both SPY and QQQ on every declared
session. The calendar CSV has one `date` column. The source receipt must be
complete and bind both input fingerprints; the runner rejects a shortened
2009–2025 horizon. The calendar is a current XNYS historical schedule from
exchange_calendars, not original exchange release evidence. Failed retrieval
preserves a failure receipt; it never substitutes invented prices for real data.

Output includes `protocol.json`, `manifest.json`, metrics, paired inference,
training summary, two figures and a report. Each asset has features, probabilities,
training events, parameter snapshots, targets, and all six scenarios' ledgers,
decisions and trades. Output fingerprints and code/dependency versions are recorded.
Current-vintage Yahoo inputs and derived real artifacts remain private pending
their particular dissemination rights. See [provenance](REGIME_PROVENANCE.md).
