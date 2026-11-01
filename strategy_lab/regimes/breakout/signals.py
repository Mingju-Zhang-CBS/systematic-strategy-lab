"""Prior-bar channels, explicit persistent state and unchanged HMM overlays."""
import numpy as np
import pandas as pd
from .config import BreakoutConfig,SIGNALS


def channel_signal(bars,window,pulse=False,rtol=1e-12):
    if isinstance(window,bool) or not isinstance(window,int) or window<2:
        raise ValueError("Integer channel window >=2 required")
    if not np.isfinite(rtol) or rtol<0:raise ValueError("Nonnegative comparison tolerance required")
    upper=bars.adjusted_high.rolling(window,min_periods=window).max().shift(1)
    lower=bars.adjusted_low.rolling(window,min_periods=window).min().shift(1)
    close=bars.adjusted_close
    entry=(close>upper*(1+rtol)).fillna(False)
    exit_=(close<lower*(1-rtol)).fillna(False)
    held=False;position=[]
    for entered,exited,available in zip(entry,exit_,upper.notna()&lower.notna()):
        if not available:held=False
        elif pulse:held=bool(entered)
        elif exited:held=False
        elif entered:held=True
        position.append(float(held))
    return pd.DataFrame({"upper":upper,"lower":lower,"entry":entry,"exit":exit_,"trend_state":position},index=bars.index)


def make_targets(bars,features,states,cfg=BreakoutConfig(),target_vol=.15):
    cfg.validate()
    s=states.set_index("date");f=features.loc[s.index]
    volatility=f.volatility.to_numpy()
    scale=np.divide(target_vol,volatility,out=np.zeros_like(volatility),where=volatility>0)
    scale=np.clip(scale,0,1)
    gate=(s.status.eq("ok")&(s.weighted_state_log_return>0)).to_numpy()
    weights=pd.DataFrame({"buy_hold":np.ones(len(s)),"vol_hold":scale},index=s.index)
    signals=[]
    for name,window,pulse in SIGNALS:
        full=channel_signal(bars,window,pulse,cfg.comparison_rtol)
        active=full.loc[s.index].trend_state.to_numpy()
        weights[name+"__breakout"]=active
        weights[name+"__vol_breakout"]=active*scale
        weights[name+"__hmm_breakout"]=active*gate
        weights[name+"__hmm_vol_breakout"]=active*gate*scale
        record=full.copy();record.insert(0,"specification",name);signals.append(record.reset_index())
    return weights,pd.concat(signals,ignore_index=True)
