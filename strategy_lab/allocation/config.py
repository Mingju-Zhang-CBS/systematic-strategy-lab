"""Predetermined protocol, not selected from historical performance."""
from dataclasses import asdict, dataclass, replace
import math

ASSETS = ("SPY", "EFA", "IEF", "GLD", "DBC")
METHODS = ("equal_weight", "min_variance", "mean_variance", "black_litterman",
           "risk_budget", "return_tilted_budget")
SEGMENTS = {"development": ("2013-01-01", "2017-12-31"),
            "validation": ("2018-01-01", "2020-12-31"),
            "confirmation": ("2021-01-01", "2025-12-31"),
            "full": ("2013-01-01", "2025-12-31")}
COMPARISONS = (("black_litterman", "mean_variance"),
               ("return_tilted_budget", "risk_budget"),
               ("min_variance", "equal_weight"))


@dataclass(frozen=True)
class AllocationConfig:
    lookback: int = 756
    rebalance_every: int = 21
    covariance: str = "ledoit_wolf"
    weight_cap: float = .4
    target_vol: float = .1
    risk_aversion: float = 5.
    confidence: float = .5
    tau: float = .05
    tilt: float = .5
    covariance_ridge: float = 1e-8
    solver_ftol: float = 1e-12
    optimality_tolerance: float = 2e-5
    max_iterations: int = 1000
    initial_nav: float = 100_000.
    seed: int = 42
    perturbations: int = 4
    bootstrap_samples: int = 2000

    def validate(self, n=5):
        for name in ("lookback", "rebalance_every", "max_iterations", "seed", "perturbations", "bootstrap_samples"):
            x = getattr(self, name)
            if isinstance(x, bool) or not isinstance(x, int) or x < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.lookback < 20 or self.covariance not in {"sample", "ledoit_wolf"}:
            raise ValueError("Invalid estimation window or covariance estimator")
        for name, x in asdict(self).items():
            if isinstance(x, (int, float)) and not math.isfinite(x):
                raise ValueError(f"{name} must be finite")
        if not 1/n <= self.weight_cap <= 1 or not 0 <= self.confidence < 1 or self.tilt < 0:
            raise ValueError("Invalid weight cap, confidence, or return tilt")
        if min(self.target_vol, self.risk_aversion, self.tau, self.covariance_ridge,
               self.solver_ftol, self.optimality_tolerance, self.initial_nav) <= 0:
            raise ValueError("Positive model scales required")


def variants(cfg):
    """23 specifications; every sensitivity is retained, never ranked for selection."""
    result = [(method, method, cfg, False) for method in METHODS]
    for prefix, changed in (("sample", replace(cfg, covariance="sample")),
                            ("short", replace(cfg, lookback=252))):
        result += [(prefix+"__"+method, method, changed, False) for method in METHODS]
    result += [("bl_low_confidence", "black_litterman", replace(cfg, confidence=.25), False),
               ("bl_high_confidence", "black_litterman", replace(cfg, confidence=.75), False),
               ("bl_reversed_views", "black_litterman", cfg, True),
               ("budget_low_tilt", "return_tilted_budget", replace(cfg, tilt=.25), False),
               ("budget_high_tilt", "return_tilted_budget", replace(cfg, tilt=1.), False)]
    return result
