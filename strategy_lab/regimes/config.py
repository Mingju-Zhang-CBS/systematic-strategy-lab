"""Fixed first-study protocol. No parameter is selected from reported returns."""
from dataclasses import asdict, dataclass
import math

STRATEGIES = ("buy_hold", "vol_hold", "raw_momentum", "ema_momentum",
              "kalman_momentum", "kalman_hmm")
SEGMENTS = {"development": ("2013-01-01", "2017-12-31"),
            "validation": ("2018-01-01", "2020-12-31"),
            "confirmation": ("2021-01-01", "2025-12-31"),
            "full": ("2013-01-01", "2025-12-31")}


@dataclass(frozen=True)
class RegimeConfig:
    momentum: int = 20
    volatility: int = 20
    train_window: int = 756
    refit_every: int = 21
    states: int = 3
    process_variance: float = 1e-5
    measurement_variance: float = .001
    target_vol: float = .15
    initial_nav: float = 100_000.
    seed: int = 42
    max_iterations: int = 500
    tolerance: float = .001
    bootstrap_samples: int = 2000

    def validate(self):
        for name in ("momentum", "volatility", "train_window", "refit_every",
                     "states", "seed", "max_iterations", "bootstrap_samples"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.states != 3 or self.volatility < 2 or self.train_window < 20:
            raise ValueError("Three states, volatility >=2, training >=20 required")
        for name in ("process_variance", "measurement_variance", "target_vol",
                     "initial_nav", "tolerance"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")

    def to_dict(self):
        self.validate()
        return asdict(self)
