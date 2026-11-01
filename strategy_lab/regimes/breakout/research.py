"""Reuse the audited HMM and funded engine; replace only the trend signal."""
from ..config import RegimeConfig
from ..models import features,online_states
from ..engine import backtest
from .config import BreakoutConfig,names
from .signals import make_targets


def prepare_asset(bars,cfg=BreakoutConfig()):
    parent=RegimeConfig()
    close=bars.adjusted_close
    # Compute the unchanged parent features/states before joining OHLC signals.
    f=features(close,parent)
    states,fits,snapshots=online_states(f,"2013-01-01",parent)
    weights,signals=make_targets(bars,f,states,cfg,parent.target_vol)
    return f,states,fits,snapshots,weights,signals


def run_account(prices,weights,strategy,cost_bps=5.,cash_rate=0.):
    if strategy not in names():raise ValueError("Known breakout experiment strategy required")
    # The shared engine label selects one initial buy versus daily frozen
    # requests only; all actual targets come from the breakout module.
    mode="buy_hold" if strategy=="buy_hold" else "vol_hold"
    return backtest(prices,weights,RegimeConfig(),mode,cost_bps,cash_rate)
