# Robust asset allocation: forecasts, risk budgets and implementation

**Question.** How sensitive are return-driven and risk-driven allocations to
estimation error, investor-view confidence, concentration limits and costs?
This is a robustness study of familiar allocation methods, not a claim of a new
minimax or distributionally robust optimizer.

[Frozen protocol](ALLOCATION_PROTOCOL.json) · [Invented results](../reports/allocation-synthetic/REPORT.md) ·
[Tests](../tests/test_allocation.py) · [Validation](ALLOCATION_VALIDATION.md) ·
[Chinese learning notes](ALLOCATION_LEARNING_CN.md) · [Provenance](ALLOCATION_PROVENANCE.md)

## Common experiment

The five USD ETF roles are SPY (U.S. equities), EFA (developed international
equities), IEF (intermediate Treasuries), GLD (gold) and DBC (commodity exposure).
The real reference requests 2009–2025 current-vintage adjusted closes; evaluation
starts in 2013. The selected surviving ETFs are a fixed illustrative universe,
not a point-in-time investable-universe reconstruction or every asset class.
In the public fixture these tickers name invented roles, not actual ETF prices.

All methods estimate from 756 daily arithmetic returns through decision close t,
annualizing mean by 252. Rebalance every 21 supplied sessions from the first
2013 session. Normalize each risky sleeve to 100%, with nonnegative weights and
a 40% per-asset cap. Scale the sleeve by `min(1, 0.10 / predicted_volatility)`;
the remainder is cash. There is no borrowing or shorting. This shared scaling
procedure does not imply equal realized volatility or equal invested exposure.
Caps apply to requested sleeve weights; holdings can drift between rebalances.

Primary covariance is Ledoit–Wolf, fitted to the training window. Sample
covariance is a declared sensitivity. Both receive a fixed diagonal ridge of
`1e-8 * mean(diagonal(annual_covariance))`, recorded in the protocol. Zero/invalid
variance fails instead of inventing a risk estimate. Means, covariance, shrinkage,
effective forecasts, weights and solver diagnostics accompany each successful
decision. Canonical data layout and one numerical thread stabilize fingerprints.

## Six methods

| Method | Risky-sleeve objective |
|---|---|
| Equal weight | 20% per asset before common risk scaling |
| Minimum variance | Minimize portfolio variance with common caps |
| Mean–variance | Maximize `mu'w - delta/2 * w'Sigma w`, delta=5 |
| Black–Litterman | Same mean–variance optimizer and same Sigma; replace mu with the posterior mean |
| Bounded risk budgeting | Convex log-barrier risk-budget solve; normalize auxiliary exposures to sleeve weights |
| Return-tilted risk budgeting | Add a dimensionless return reward to the same convex risk-budget objective |

### Black–Litterman: views must reach the objective

The prior is `pi = delta * Sigma * w_reference`, where the reference is explicitly
equal weight. These are reverse-implied policy-reference returns, **not** market
equilibrium returns extracted from contemporaneous market capitalizations.
No current market-cap snapshot is backfilled over earlier years.

Each asset has a named absolute annual arithmetic-return view, Q, equal to its
trailing historical mean. This is an inspectable noisy estimator, not an informed
investor forecast or future return. Build the picking matrix P from asset labels,
not positional assumptions. Unknown labels fail. The public function also accepts
named relative views, checked against an independent precision-matrix calculation.

With tau=0.05 and confidence c=0.5:

```text
C = tau * Sigma
Omega = diagonal(diagonal(P C P')) * (1-c)/c
posterior_mean = pi + C P' solve(P C P' + Omega, Q - P pi)
posterior_uncertainty = C - C P' solve(P C P' + Omega, P C)
```

Zero confidence returns the prior. The proportional Omega makes posterior means
independent of tau; tau is not searched to produce a stronger result. Posterior
uncertainty is reported diagnostically. The main allocation uses the same Sigma
as other methods to isolate changes in forecasts. Using a minimum-variance
objective would bypass return views; here the return-aware utility makes their
role explicit. See the upstream [BL method reference](https://pyportfolioopt.readthedocs.io/en/latest/BlackLitterman.html).

### Risk budgets and a carefully defined return tilt

Let `v = trace(Sigma)/N`, `C = Sigma/v`, `m = mu/sqrt(v)`, and equal risk budgets
`b_i = 1/N`. Solve in strictly positive auxiliary exposures x:

```text
minimize 0.5*x'C*x - sum_i b_i*log(x_i) - eta*m'x
subject to x_i <= 0.4 * sum_j x_j
w = x / sum(x)
```

Use eta=0 for bounded risk budgeting and eta=0.5 for the return-tilted method.
The quadratic is positive definite, the negative-log barrier is convex and the
return reward is linear. The cap constraints are homogeneous and linear.
Normalizing both covariance and mean makes eta dimensionless; it is not a
percentage split between differently scaled errors and returns. The auxiliary
exposure magnitude is not actual account leverage; normalize before applying
the common risk control. The tilted method is RRP-inspired and deliberately
defined here, not asserted to reproduce a unique published relaxed-RP model.

Without binding caps and eta=0, the solution has equal fractional risk
contributions. With diagonal covariance it reduces to inverse-volatility weights.
Binding caps can prevent exact parity. Report the observed residual rather than
calling it exact equal risk. For every sleeve:

```text
volatility = sqrt(w' Sigma w)
absolute contribution_i = w_i * (Sigma w)_i / volatility
fractional contribution_i = w_i * (Sigma w)_i / (w' Sigma w)
```

Absolute contributions sum to volatility; fractions sum to one. Individual
fractions can be negative for hedging assets in general portfolios. The L2
distance from equal fractions is a diagnostic, not an unreported constraint.

## Numerical acceptance and failures

All nontrivial methods use SciPy SLSQP with analytic gradients, maximum 1,000
iterations and objective tolerance `1e-12`. A success flag alone is insufficient.
Validate finite, feasible normalized weights. For the quadratic objectives,
compute the convex first-order gap using the exact greedy linear minimizer on
the capped simplex. For the risk-budget objectives, independently fit nonnegative
multipliers to active homogeneous constraints and check stationarity, primal
feasibility and complementarity. The acceptance residual is at most `2e-5`.
These are numerical acceptance diagnostics, not a proof that arbitrary future
solver inputs will succeed. Warnings, residuals and reasons remain visible.

An invalid covariance or rejected solution requests all cash for that method at
that rebalance. The normal one-session execution delay still applies; a failure
does not instantly flatten the account. Do not delete dates, reuse an old answer
silently, replace it with equal weight or select another start by realized return.
The next scheduled rebalance can recover. Controlled perturbation failures are
reported separately rather than treated as successful stable weights.

## Noisy forecasts and predeclared sensitivities

The 23 specifications are six primary methods, the same six with sample
covariance, the same six with a 252-session window, BL at 25%/75% confidence,
BL with reversed views, and return-tilt eta at 0.25/1.0. Cost and cash scenarios
are crossed with every specification. Forecasts stay anchored to a zero-rate
reference; changing the account cash scenario does not retune target weights.

At each primary rebalance, add four date-seeded independent normal shocks to
the annual mean vector, fixing covariance. Component scale is
`sqrt(252 * Sigma_ii / lookback)`. This is an IID sampling-error approximation
used as a **stress size**, not an estimated forecast-error distribution or valid
dependent-data confidence interval. Recompute the three return-aware methods.
Mean-independent methods are deliberate zero-response controls. Report sleeve
and post-risk-scaling half-L1 distances, failed draws, medians and 95th percentiles.
No perturbed outcome is used to select a model or modify historical orders.

## Funding and timing

After close t, freeze target fractions. Execute at the next supplied session
close t+1 using then-current equity. Old units earn the intervening price move;
new units earn returns after execution. All methods start evaluation in cash on
the same date. Cash and units continue across every calendar segment.

Use fractional **adjusted-close total-return model units**, not observed ETF
shares or executable adjusted quotes. No extra dividend is added. For pretrade
equity V, old dollar values A and fee rate c, solve the strictly monotone equation
`V_after + c * sum(abs(w*V_after - A)) = V`. Buy and sell legs both pay costs;
the cash account funds them. Target drift is included even when requested
weights have not changed. A bracketed scalar solve and an independent trade-flow
audit check account conservation. No external capital or invented terminal
liquidation is inserted; terminal units remain marked at the last model price.

Costs are 0/5/10 bp per traded dollar, including first entry. Cash accrues at
assumed continuously compounded 0% or 3% over actual calendar days/365.25.
These are scenarios, not historical deposit rates, spreads or measured fills.
An actual ETF implementation additionally needs action clocks, share units,
execution/liquidity evidence and applicable fees/taxes.

## Evaluation and inference

Development is 2013–2017, validation 2018–2020 and historical confirmation
2021–2025. These familiar historical windows are not independent prospective
evidence. Rules and sensitivities were recorded before this implementation ran
performance. Report all 23 specifications × 3 costs × 2 cash assumptions × 4
periods (552 metric rows, 138 full-period accounts), with failures retained.

Metrics include CAGR, arithmetic-excess-return Sharpe, realized volatility,
drawdown including starting wealth, traded-dollar turnover, invested exposure,
risky-sleeve HHI/effective asset count, fees and reconciliation errors. Estimated
risk fractions and optimality diagnostics are separate from realized risk.

Three fixed paired contrasts are BL minus mean–variance, tilted budgeting minus
bounded budgeting, and minimum variance minus equal weight. For all six account
scenarios and four periods, use 20/63-session noncircular moving-block bootstrap,
2,000 resamples, seed 42, truncated final blocks. Annualize the paired arithmetic
mean by 252. Retain all 144 percentile interval rows. These are descriptive,
without multiple-comparison correction; selection from the sensitivity table
would require a new study. Better concentration, stability or lower realized
risk is not by itself proof of superior predictive information or market alpha.

## Run and inspect

Python 3.12, locked dependencies:

```bash
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest tests/test_allocation.py
python -m strategy_lab.allocation --demo --output local-runs/allocation
python tools/verify_allocation_run.py local-runs/allocation
```

The fixture uses invented business days and a stylized factor process; it is
not an exchange calendar, calibrated market model or known true forecast.
The demo requires no network, key or market-data service. Use a new output folder.

For personal reference work, install `.[allocation-download]`, then:

```bash
python tools/download_allocation_prices.py --output /private/allocation-capture
python -m strategy_lab.allocation --prices /private/allocation-capture/prices.csv --sessions /private/allocation-capture/sessions.csv --source /private/allocation-capture/source.json --output /private/allocation-study
```

Prices must have exactly `date,ticker,adjusted_close`, sorted by date/ticker with
all five assets and no missing or duplicate observations on every declared
session. The calendar has one date column; the completed source receipt binds
both files. A shortened 2009–2025 horizon is rejected. No gap is replaced with
zero returns or an invented price. Real capture and real output paths must stay
outside this public repository. Current-vintage prices, their ledgers, figures
and result summaries remain private; see [data boundaries](ALLOCATION_PROVENANCE.md).

Full outputs include targets for every specification, estimation/optimization
events, parameters, risk fractions, forecast perturbations, all ledgers,
decisions/trades, summary tables, figures and a report. Manifests bind input,
protocol, source/shared-code, versions and every output fingerprint. The public
checked-in report is an explicitly documented compact **invented** snapshot.
