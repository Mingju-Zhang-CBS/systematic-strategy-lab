"""No HMM parameter, gate or risk rule is selected from breakout performance."""
from dataclasses import dataclass,asdict
import math
from ..config import RegimeConfig,SEGMENTS

ASSETS=("SPY","QQQ")
SIGNALS=(("channel55",55,False),("channel20",20,False),
         ("channel100",100,False),("pulse55",55,True))
FACTORS=("breakout","vol_breakout","hmm_breakout","hmm_vol_breakout")
COMPARISONS=(("hmm_vol_breakout","vol_breakout"),("vol_breakout","breakout"),
             ("hmm_breakout","breakout"),("hmm_vol_breakout","hmm_breakout"))


@dataclass(frozen=True)
class BreakoutConfig:
    primary_window:int=55
    comparison_rtol:float=1e-12
    envelope_seed:int=20261103

    def validate(self):
        if self.primary_window!=55 or isinstance(self.envelope_seed,bool) or not isinstance(self.envelope_seed,int) or self.envelope_seed<1:
            raise ValueError("Frozen 55-session primary channel and positive envelope seed required")
        if not math.isfinite(self.comparison_rtol) or not 0<=self.comparison_rtol<=1e-8:
            raise ValueError("Invalid numerical comparison tolerance")


def names():
    return ("buy_hold","vol_hold")+tuple(f"{signal}__{factor}" for signal,_,_ in SIGNALS for factor in FACTORS)


def protocol(cfg=BreakoutConfig()):
    cfg.validate();hmm=RegimeConfig();hmm.validate()
    return {"version":"hmm-breakout-transfer-v1","config":asdict(cfg),"hmm_config":asdict(hmm),
            "assets":list(ASSETS),"asset_roles":{"SPY":"primary","QQQ":"same-rule transfer"},
            "segments":SEGMENTS,"signal_specifications":[{"name":n,"window":w,"pulse":p} for n,w,p in SIGNALS],
            "strategies":list(names()),"primary_strategies":["buy_hold","vol_hold"]+["channel55__"+n for n in FACTORS],
            "comparisons":[{"alternative":a,"control":b} for a,b in COMPARISONS]+[{"alternative":"interaction","control":"2x2 difference-in-differences"}],
            "cost_bps":[0,5,10],"continuous_cash_rates":[0.,.03],"bootstrap_blocks":[20,63],
            "hmm_features":["log_return","volatility"],"hmm_gate":"unchanged: status ok and filtered state-weighted current log-return mean > 0",
            "channel":"prior-window adjusted highs/lows, excluding current bar; enter above upper, exit below lower, otherwise carry",
            "initialization":"signal latch starts flat at first bar, evolves through warmup; accounts start cash in 2013; no segment reset",
            "pulse_sensitivity":"hold only when current close exceeds prior 55 highs; otherwise request cash",
            "overlay":"continuous gate on independent underlying trend state; gate recovery can reenter without a new channel breakout",
            "execution":"after-close t frozen fractions execute at close t+1; adjusted model units, not ETF fills",
            "risk":"same 20-session log-return volatility, 15% target and 100% cap as parent; no shorting or leverage",
            "failure":"unchanged HMM failure requests cash until scheduled successful refit, with normal one-session fill delay",
            "parent_equivalence":"recompute unchanged HMM; compare state probabilities, fitted parameters and all buy/hold and vol/hold ledgers with bound parent",
            "synthetic_closes":"reuse parent independently invented generator, seed 20261101; add invented OHLC envelope only",
            "real_source":"derive adjusted OHLC from hash-verified archived parent provider responses and exactly the parent analyzed closes; no refreshed vintage",
            "inference":"five predeclared primary-55 contrasts including interaction; descriptive dependent-data intervals, no multiplicity adjustment",
            "evidence":"retrospective strategy/asset transfer; prior returns already inspected, no independent prospective holdout"}
