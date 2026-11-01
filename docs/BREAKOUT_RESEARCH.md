# Does the HMM transfer to a breakout signal?

This is a transfer test of the [existing daily HMM study](REGIME_RESEARCH.md).
The question is whether its **unchanged** online state gate adds information
beyond a different trend rule and the same volatility control. SPY is primary;
QQQ applies every rule without retuning. The [public experiment](../reports/breakout-synthetic/REPORT.md)
uses invented OHLC throughout. Actual Yahoo observations, fitted real models,
real result tables and derived figures remain private.

## Mechanism and fair controls

For adjusted close C, high H and low L, the primary channel is

`upper[t] = max(H[t-55:t]); lower[t] = min(L[t-55:t])`.

Python slices exclude t. After close t, enter when C[t] exceeds the upper
channel; exit below the lower channel; otherwise carry the underlying long/flat
state. Comparisons use a fixed relative tolerance of 1e-12. The latch starts
flat at the first history bar and evolves through warmup; accounts start in
cash in 2013. Period boundaries never reset signals, HMMs or accounts.

The HMM keeps the parent's two features (daily log return and past-20-session
annualized log-return volatility), three diagonal Gaussian states, 756 prior
training observations, 21-session refits, train-only standardization and seed
42. Forward recursion updates probabilities continuously. Refits exclude the
decision-day observation and re-filter their training windows to initialize
probabilities. `sum(filtered_probability * fitted_state_log_return_mean) > 0`
opens the gate; state names do not drive decisions. Failure requests cash
until a scheduled successful refit. No breakout statistic is added to training.

Let B be the independent channel latch, G the HMM gate and
`V = min(1, 0.15 / sigma20)` (zero for unavailable/nonpositive volatility).
The central comparison is a two-by-two experiment:

|Method|Target fraction|Question|
|---|---|---|
|Breakout|B|Underlying trend rule|
|Vol breakout|B × V|Effect of volatility sizing|
|HMM breakout|B × G|Effect of the gate at unit size|
|HMM + vol breakout|B × G × V|Gate increment with common sizing|

Buy-and-hold and volatility-controlled hold supply common opportunity-cost
controls. They reuse the parent funded engine and are compared with its saved
accounts when a bound parent run is supplied. The gate overlays B each day:
gate recovery may reenter a still-active trend without a new upper breakout.
Failure does not erase the channel latch. No Kalman or EMA filter is inserted
into the breakout rule; those remain in the parent momentum study.

Predeclared sensitivities retain symmetric 20- and 100-session persistent
channels and a 55-session **pulse** rule, which holds only on upper-breakout
days. All four factor methods apply to each signal specification. Including
the two controls gives 18 methods per asset, not four separately tuned models.
The protocol was fixed before breakout performance execution; the machine-readable
[protocol](BREAKOUT_PROTOCOL.json) lists every rule.

## Information, data and money clocks

History spans 2009–2025. Evaluation begins in 2013 on identical dates for all
methods: development 2013–2017, validation 2018–2020, historical confirmation
2021–2025, plus the full period. These labels are retrospective: the parent
history was already examined. This is strategy/asset transfer, not an independent
unseen holdout or prospective test.

Signals form after close t; frozen target fractions execute at close t+1.
Old units earn the return up to the execution close. The shared engine solves
the after-fee target, charges actual drift-adjusted traded notional, and checks
cash and account conservation. There are no intrabar stops or high/low fills.
Long/cash only; exposure is at most 100%. One-way costs are 0, 5 and 10 bp;
zero cash yield is primary and fixed 3% continuous ACT/365.25 is a sensitivity.
This is the parent's log-return volatility estimator, **not ATR**.

Private real bars are derived from the **archived parent capture**, not a fresh
download: divide the exact parent analyzed adjusted close by archived raw close,
then scale raw open/high/low by that factor. Provider responses, exact sessions,
parent input/output hashes and tiny parser-rounding differences are checked.
New files use round-trip float parsing so the parent's analyzed closes are
preserved exactly. Adjusted OHLC are total-return model units, not observed
executable ETF quotes. Dividends are counted once. Adjustment/revision history
is today's captured vintage, not point-in-time publication evidence.

## Results and uncertainty

Each full run writes 216 accounts, 864 metric rows and 480 paired-interval rows.
Metrics include net total return/CAGR, standard excess-return Sharpe, drawdown,
turnover, actual volatility, average held/end exposure, costs and account residuals.
Training diagnostics retain failures and cash requests.

Five primary-55 contrasts are fixed: HMM increment with volatility control,
volatility increment without HMM, HMM increment at unit size, volatility increment
with HMM, and the two-by-two interaction. The last is a descriptive
difference-in-differences, not a causal treatment effect. Each uses paired daily
**net** returns, 2,000 noncircular moving-block resamples with blocks 20/63,
seed 42, and 95% percentile intervals for annualized arithmetic mean differences.
Exposure differences accompany every comparison. These are not CAGR confidence
intervals, equal-risk tests or multiple-testing-adjusted significance claims.

All periods, costs, cash cases and sensitivities survive the report, including
losses and intervals covering zero. Invented results demonstrate mechanics;
they cannot answer whether HMM adds value in actual markets. Real findings
are interpreted in the private report and do not determine published rules.

## Reproduce offline

```bash
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest
python -m strategy_lab.regimes --demo --output local-runs/parent
python -m strategy_lab.regimes.breakout --demo --parent local-runs/parent --output local-runs/breakout
python tools/verify_breakout_run.py local-runs/breakout
python tools/verify_breakout_run.py reports/breakout-synthetic
```

Python 3.12 and the existing locked HMM dependencies are reused; no new
dependency is introduced. A standalone demo may omit `--parent`; its manifest
then explicitly records that no saved-parent equivalence was checked. Real
inputs require a complete receipt, declared sessions and a bound parent:

```bash
python tools/prepare_breakout_bars.py --capture /private/parent-capture --parent /private/parent-run --output /private/bars
python -m strategy_lab.regimes.breakout --bars /private/bars/bars.csv --sessions /private/bars/sessions.csv --source /private/bars/source.json --parent /private/parent-run --output /private/breakout
```

The bar schema is exactly `date,ticker,adjusted_open,adjusted_high,adjusted_low,adjusted_close`;
rows must be ordered, unique, finite, positive, satisfy OHLC containment and
cover both assets on every declared session. Missing or incomplete history is
rejected; the predeclared sample is not silently shortened. Use new output
directories. Full runs save features, channels, probabilities, training events,
model snapshots, targets, decisions, trades, ledgers, metrics, intervals, figures,
protocol, parent-equivalence receipt and artifact/version fingerprints.

[Chinese learning notes](BREAKOUT_LEARNING_CN.md) · [Source and contribution](BREAKOUT_PROVENANCE.md)
· [Validation](BREAKOUT_VALIDATION.md) · [Compact invented snapshot](../reports/breakout-synthetic/SNAPSHOT.md)
