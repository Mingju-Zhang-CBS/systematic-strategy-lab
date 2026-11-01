"""Label-aligned BL and convex allocation objectives with optimality diagnostics."""
from dataclasses import dataclass
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize, nnls
from sklearn.covariance import LedoitWolf
from threadpoolctl import threadpool_limits
from .config import AllocationConfig, METHODS


def checked_covariance(cov):
    if (not isinstance(cov, pd.DataFrame) or cov.empty or cov.index.has_duplicates
            or not cov.index.equals(cov.columns)):
        raise ValueError("Square covariance with unique aligned asset labels required")
    x = cov.to_numpy(float)
    if not np.isfinite(x).all() or not np.allclose(x, x.T, atol=1e-12, rtol=1e-10):
        raise ValueError("Finite symmetric covariance required")
    if np.linalg.eigvalsh(x).min() <= 0:
        raise ValueError("Strictly positive definite covariance required")
    return x


def estimate(returns, cfg):
    cfg.validate(returns.shape[1])
    # Canonical memory layout and one BLAS thread make prefix fingerprints
    # independent of how pandas copied an otherwise identical past window.
    x = np.array(returns.to_numpy(float),dtype=float,order="C",copy=True)
    if len(x) != cfg.lookback or not np.isfinite(x).all() or returns.columns.has_duplicates:
        raise ValueError("Complete labelled training window required")
    with threadpool_limits(limits=1):
        if cfg.covariance == "ledoit_wolf":
            estimator = LedoitWolf().fit(x)
            cov = estimator.covariance_*252
            shrinkage = float(estimator.shrinkage_)
        else:
            cov = np.cov(x, rowvar=False, ddof=1)*252
            shrinkage = 0.
    reference = float(np.trace(cov)/len(cov))
    if not np.isfinite(reference) or reference <= 1e-14:
        raise ValueError("Degenerate training covariance")
    cov = (cov+cov.T)/2 + np.eye(len(cov))*reference*cfg.covariance_ridge
    covariance = pd.DataFrame(cov, index=returns.columns, columns=returns.columns)
    checked_covariance(covariance)
    return pd.Series(x.mean(axis=0)*252, index=returns.columns), covariance, shrinkage


def black_litterman(cov, prior, views, confidence=.5, tau=.05):
    """Views have named picks. Return posterior mean and uncertainty, not weights."""
    sigma = checked_covariance(cov)
    if not isinstance(prior, pd.Series) or set(prior.index) != set(cov.index) or prior.index.has_duplicates:
        raise ValueError("One prior per named asset required")
    pi = prior.reindex(cov.index).to_numpy(float)
    if not np.isfinite(pi).all() or not np.isfinite([confidence, tau]).all() or not 0 <= confidence < 1 or tau <= 0:
        raise ValueError("Invalid prior, confidence or tau")
    rows = []; q = []
    for view in views:
        if not view["picks"] or set(view["picks"])-set(cov.index):
            raise ValueError("View refers to missing asset labels")
        row = np.array([view["picks"].get(asset, 0.) for asset in cov.index], dtype=float)
        if not np.isfinite(row).all() or not np.any(row):
            raise ValueError("Nonzero finite view picks required")
        rows.append(row); q.append(float(view["annual_return"]))
    if not np.isfinite(q).all():
        raise ValueError("Finite annual return views required")
    c = tau*sigma
    if not rows or confidence == 0:
        return pd.Series(pi, index=cov.index), pd.DataFrame(c, index=cov.index, columns=cov.index)
    p = np.array(rows); q = np.array(q)
    omega = np.diag(np.diag(p@c@p.T)*(1-confidence)/confidence)
    middle = p@c@p.T+omega
    posterior = pi+c@p.T@np.linalg.solve(middle, q-p@pi)
    uncertainty = c-c@p.T@np.linalg.solve(middle, p@c)
    return (pd.Series(posterior, index=cov.index),
            pd.DataFrame((uncertainty+uncertainty.T)/2, index=cov.index, columns=cov.index))


def risk_contributions(weights, cov):
    w = np.asarray(weights, float); sigma = np.asarray(cov, float)
    variance = float(w@sigma@w)
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("Positive portfolio variance required")
    absolute = w*(sigma@w)/np.sqrt(variance)
    fractions = w*(sigma@w)/variance
    return absolute, fractions


def linear_minimum(gradient, cap):
    """Exact linear minimizer on the capped simplex, for a convex optimality gap."""
    v = np.zeros(len(gradient)); left = 1.
    for i in np.argsort(gradient, kind="stable"):
        v[i] = min(cap, left); left -= v[i]
    if left > 1e-10:
        raise ValueError("Infeasible capped simplex")
    return v


@dataclass
class Solution:
    weights: pd.Series
    expected_returns: pd.Series
    diagnostics: dict


def allocate(mean, cov, method, cfg=AllocationConfig(), reverse_views=False):
    sigma = checked_covariance(cov); n = len(cov); cfg.validate(n)
    if method not in METHODS or not isinstance(mean, pd.Series) or mean.index.has_duplicates or set(mean.index) != set(cov.index):
        raise ValueError("Known method and labelled mean required")
    mu = mean.reindex(cov.index).to_numpy(float)
    if not np.isfinite(mu).all():
        raise ValueError("Finite annualized arithmetic means required")
    equal = np.ones(n)/n
    reference = float(np.trace(sigma)/n); normal = sigma/reference
    effective_mu = mu.copy(); uncertainty = None
    if method == "black_litterman":
        prior = cfg.risk_aversion*sigma@equal
        views = [{"picks":{asset:1.}, "annual_return":float((-1 if reverse_views else 1)*value)}
                 for asset,value in zip(cov.index,mu)]
        posterior, uncertainty = black_litterman(cov,pd.Series(prior,index=cov.index),views,cfg.confidence,cfg.tau)
        effective_mu = posterior.to_numpy()
    info = {"method":method, "success":True, "iterations":0, "objective":None,
            "optimality_residual":0., "solver_warnings":[], "bl_mean_shift_l2":float(np.linalg.norm(effective_mu-mu))}
    if method == "equal_weight":
        w = equal
    elif method in {"min_variance", "mean_variance", "black_litterman"}:
        if method == "min_variance":
            hessian = normal; linear = np.zeros(n)
        else:
            hessian = cfg.risk_aversion*sigma/np.sqrt(reference)
            linear = effective_mu/np.sqrt(reference)
        def objective(w):return .5*w@hessian@w-linear@w
        def gradient(w):return hessian@w-linear
        with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = minimize(objective,equal,jac=gradient,method="SLSQP",bounds=[(0.,cfg.weight_cap)]*n,
                              constraints={"type":"eq","fun":lambda w:w.sum()-1,"jac":lambda w:np.ones(n)},
                              options={"ftol":cfg.solver_ftol,"maxiter":cfg.max_iterations})
        w = result.x
        g = gradient(w); residual = max(0.,float(g@(w-linear_minimum(g,cfg.weight_cap))))
        info.update(iterations=int(result.nit), objective=float(objective(w)), optimality_residual=residual,
                    solver_warnings=[str(item.message) for item in caught])
        if not result.success or residual > cfg.optimality_tolerance:
            raise FloatingPointError(f"QP rejected: {result.message}; gap={residual:.8g}")
    else:
        # Both objectives are convex in positive unnormalized exposures x.
        # Normalize covariance and means so the tilt has a dimensionless meaning.
        eta = cfg.tilt if method == "return_tilted_budget" else 0.
        score = mu/np.sqrt(reference)
        budget = equal
        a = cfg.weight_cap*np.ones((n,n))-np.eye(n)
        def objective(x):return .5*x@normal@x-budget@np.log(x)-eta*score@x
        def gradient(x):return normal@x-budget/x-eta*score
        initial = equal/np.sqrt(equal@normal@equal)
        with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = minimize(objective,initial,jac=gradient,method="SLSQP",bounds=[(1e-10,None)]*n,
                              constraints={"type":"ineq","fun":lambda x:a@x,"jac":lambda x:a},
                              options={"ftol":cfg.solver_ftol,"maxiter":cfg.max_iterations})
        x = result.x; slack = a@x; g = gradient(x)
        active = a[slack < 1e-6].T
        if active.shape[1]:
            multipliers,_ = nnls(active,g,maxiter=1000)
            stationarity = float(np.max(np.abs(g-active@multipliers)))
            complementarity = float(np.max(np.abs(multipliers*slack[slack < 1e-6])))
        else:stationarity=float(np.max(np.abs(g)));complementarity=0.
        residual = max(stationarity,complementarity,max(0.,float(-slack.min())))
        info.update(iterations=int(result.nit),objective=float(objective(x)),optimality_residual=residual,
                    solver_warnings=[str(item.message) for item in caught], tilt=eta)
        if not result.success or not np.isfinite(x).all() or (x <= 1e-9).any() or residual > cfg.optimality_tolerance:
            raise FloatingPointError(f"Risk-budget solve rejected: {result.message}; KKT={residual:.8g}")
        w = x/x.sum()
    if (not np.isfinite(w).all() or abs(w.sum()-1) > 1e-8 or w.min() < -1e-9
            or w.max() > cfg.weight_cap+1e-8):
        raise FloatingPointError("Optimizer returned infeasible weights")
    # Remove only floating-point boundary noise; reject before this normalization.
    w = np.maximum(w,0);w /= w.sum()
    _, fractions = risk_contributions(w,sigma)
    info.update(risk_fraction_l2=float(np.linalg.norm(fractions-equal)),
                predicted_vol=float(np.sqrt(w@sigma@w)), hhi=float(w@w),
                effective_assets=float(1/(w@w)), max_weight=float(w.max()),
                posterior_uncertainty_trace=float(np.trace(uncertainty)) if uncertainty is not None else None)
    return Solution(pd.Series(w,index=cov.index),pd.Series(effective_mu,index=cov.index),info)
