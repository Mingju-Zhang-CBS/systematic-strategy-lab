"""Training-only Gaussian HMM parameters and causal forward probabilities."""
from dataclasses import dataclass
import warnings
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from threadpoolctl import threadpool_limits
from .config import RegimeConfig


def steady_gain(q, r):
    if not np.isfinite([q, r]).all() or min(q, r) <= 0:
        raise ValueError("Positive finite variances required")
    posterior = (np.sqrt(q*q+4*q*r)-q)/2
    return (posterior+q)/(posterior+q+r)


def smooth_log_index(values, q, r):
    values = np.asarray(values, float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Finite nonempty one-dimensional log index required")
    kalman = np.empty(len(values)); ema = np.empty(len(values))
    kalman[0] = ema[0] = values[0]
    posterior = 1.
    gain = steady_gain(q, r)
    for i in range(1, len(values)):
        predicted = posterior+q
        k = predicted/(predicted+r)
        kalman[i] = kalman[i-1]+k*(values[i]-kalman[i-1])
        posterior = (1-k)*predicted
        ema[i] = ema[i-1]+gain*(values[i]-ema[i-1])
    return kalman, ema


def features(prices, cfg):
    log_index = np.log(np.asarray(prices, float)/float(prices.iloc[0]))
    kalman, ema = smooth_log_index(log_index, cfg.process_variance, cfg.measurement_variance)
    d = pd.DataFrame(index=prices.index)
    d["log_return"] = pd.Series(log_index, index=prices.index).diff()
    d["volatility"] = d.log_return.rolling(cfg.volatility).std(ddof=1)*np.sqrt(252)
    for name, values in (("raw", log_index), ("ema", ema), ("kalman", kalman)):
        d[name+"_log_index"] = values
        d[name+"_momentum"] = d[name+"_log_index"].diff(cfg.momentum)
    return d


def check_probabilities(values, ndim):
    x = np.asarray(values, float)
    if x.ndim != ndim or not np.isfinite(x).all() or (x < 0).any():
        raise ValueError("Invalid probabilities")
    sums = x.sum(axis=-1)
    if not np.allclose(sums, 1., atol=1e-10, rtol=0):
        raise ValueError("Probabilities must sum to one")
    return x


def forward_step(log_emission, transition, previous=None, start=None):
    """p(S_t | observations through t); first observation has no transition."""
    a = check_probabilities(transition, 2)
    prior = check_probabilities(start, 1) if previous is None else check_probabilities(previous, 1) @ a
    e = np.asarray(log_emission, float)
    if a.shape != (len(prior), len(prior)) or e.shape != prior.shape or not np.isfinite(e).all():
        raise ValueError("Invalid emission or transition dimensions")
    with np.errstate(divide="ignore"):
        logp = np.log(prior)+e
    normalizer = logsumexp(logp)
    if not np.isfinite(normalizer):
        raise FloatingPointError("Impossible observation")
    return np.exp(logp-normalizer)


@dataclass
class FittedHMM:
    center: np.ndarray
    scale: np.ndarray
    start: np.ndarray
    transition: np.ndarray
    means: np.ndarray
    variances: np.ndarray
    raw_return_means: np.ndarray
    iterations: int
    last_gain: float
    fit_warnings: list

    def emission(self, observation):
        x = (np.asarray(observation, float)-self.center)/self.scale
        out = -.5*np.sum(np.log(2*np.pi*self.variances)+(x-self.means)**2/self.variances, axis=1)
        if not np.isfinite(out).all():
            raise FloatingPointError("Nonfinite emission")
        return out

    def step(self, observation, previous=None):
        return forward_step(self.emission(observation), self.transition, previous, self.start)

    def serializable(self):
        return {key: value.tolist() if isinstance(value, np.ndarray) else value
                for key, value in vars(self).items()}


def fit_hmm(observations, cfg: RegimeConfig):
    cfg.validate()
    x = np.asarray(observations, float)
    if x.shape != (cfg.train_window, 2) or not np.isfinite(x).all():
        raise ValueError("Complete fixed training window required")
    center = x.mean(axis=0); scale = x.std(axis=0, ddof=0)
    if (scale <= 1e-12).any():
        raise ValueError("Degenerate training feature")
    z = (x-center)/scale
    model = GaussianHMM(n_components=cfg.states, covariance_type="diag",
                        n_iter=cfg.max_iterations, tol=cfg.tolerance,
                        random_state=cfg.seed, min_covar=1e-4, implementation="log")
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(z)
    history = list(model.monitor_.history)
    if len(history) < 2 or not np.isfinite(history).all():
        raise FloatingPointError("Invalid EM likelihood history")
    gain = history[-1]-history[-2]
    if not -cfg.tolerance <= gain < cfg.tolerance:
        raise FloatingPointError(f"EM tolerance not reached: last_gain={gain:.8g}")
    # hmmlearn exposes diagonal covariances expanded as K x D x D.
    variance = np.diagonal(model.covars_, axis1=1, axis2=2).copy()
    raw_means = model.means_[:, 0]*scale[0]+center[0]
    order = np.argsort(raw_means, kind="stable")
    fitted = FittedHMM(center, scale, model.startprob_[order],
                       model.transmat_[order][:, order], model.means_[order],
                       variance[order], raw_means[order], int(model.monitor_.iter),
                       float(gain), [str(w.message) for w in caught])
    check_probabilities(fitted.start, 1); check_probabilities(fitted.transition, 2)
    if not np.isfinite(fitted.variances).all() or (fitted.variances <= 0).any():
        raise FloatingPointError("Invalid state covariance")
    return fitted


def online_states(f, start, cfg, fitter=fit_hmm):
    """Refit using [t-window,t); refilter that window under the new model."""
    cfg.validate()
    x = f[["log_return", "volatility"]].to_numpy()
    first = f.index.get_indexer([pd.Timestamp(start)], method="bfill")[0]
    valid = np.flatnonzero(np.isfinite(x).all(axis=1))
    if first < 0 or not len(valid) or first-cfg.train_window < valid[0]:
        raise ValueError("Evaluation start lacks a full training warmup")
    model = None; probability = None; model_id = None
    records = []; fits = []; snapshots = []
    for i in range(first, len(f)):
        status = "ok"; reason = ""
        if (i-first) % cfg.refit_every == 0:
            model = None; probability = None
            model_id = f"fit-{i-first:05d}"
            training = x[i-cfg.train_window:i]
            fit_record = {"model_id": model_id, "decision_date": str(f.index[i].date()),
                          "train_start": str(f.index[i-cfg.train_window].date()),
                          "train_end": str(f.index[i-1].date()), "status": "failed", "reason": ""}
            try:
                candidate = fitter(training, cfg)
                tail = None
                for row in training:
                    tail = candidate.step(row, tail)
                model, probability = candidate, tail
                fit_record.update(status="ok", iterations=candidate.iterations, last_gain=candidate.last_gain)
                snapshots.append({**fit_record, "parameters": candidate.serializable(),
                                  "training_tail_probability": tail.tolist()})
            except (ValueError, FloatingPointError, ArithmeticError, np.linalg.LinAlgError) as error:
                fit_record["reason"] = f"{type(error).__name__}: {error}"
            fits.append(fit_record)
        expected = np.nan
        if model is not None:
            try:
                probability = model.step(x[i], probability)
                expected = float(probability @ model.raw_return_means)
                if not np.isfinite(expected):
                    raise FloatingPointError("Nonfinite weighted state mean")
            except (ValueError, FloatingPointError, ArithmeticError, np.linalg.LinAlgError) as error:
                model = None; probability = None
                reason = f"{type(error).__name__}: {error}"
        if model is None:
            status = "cash_requested"
            if not reason:
                reason = fits[-1]["reason"] or "Model unavailable until scheduled refit"
        records.append({"date": f.index[i], "model_id": model_id, "status": status,
                        "reason": reason, "weighted_state_log_return": expected,
                        **{f"p_{s}": float(probability[s]) if model is not None else np.nan
                           for s in range(cfg.states)}})
    return pd.DataFrame(records), pd.DataFrame(fits), snapshots
