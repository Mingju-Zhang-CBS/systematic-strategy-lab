"""Fixed chronological targets, diagnostics and controlled forecast perturbations."""
import numpy as np
import pandas as pd
from .config import AllocationConfig, ASSETS, METHODS, variants
from .models import allocate, estimate, risk_contributions


def make_targets(prices, cfg=AllocationConfig(), start="2013-01-01", perturb=True):
    cfg.validate(prices.shape[1])
    if tuple(prices.columns)!=ASSETS:
        raise ValueError("Canonical labelled asset columns required")
    returns=prices.pct_change(fill_method=None)
    first=prices.index.get_indexer([pd.Timestamp(start)],method="bfill")[0]
    if first < cfg.lookback or first < 252:
        raise ValueError("Evaluation start lacks full warmup")
    schedules={name:[] for name,_,_,_ in variants(cfg)}
    diagnostics=[];snapshots=[];shocks=[]
    for i in range(first,len(prices),cfg.rebalance_every):
        date=prices.index[i];cache={};base_solutions={}
        for name,method,settings,reversed_views in variants(cfg):
            key=(settings.lookback,settings.covariance)
            record={"variant":name,"method":method,"decision_date":str(date.date()),
                    "train_start":str(prices.index[i-settings.lookback+1].date()),
                    "train_end":str(date.date()),"observations":settings.lookback,
                    "covariance":settings.covariance,"confidence":settings.confidence,
                    "tilt":settings.tilt,"reverse_views":reversed_views,"status":"cash_requested","reason":""}
            weights=np.zeros(len(ASSETS));snapshot=None
            try:
                if key not in cache:
                    window=returns.iloc[i-settings.lookback+1:i+1]
                    cache[key]=estimate(window,settings)
                mean,cov,shrinkage=cache[key]
                solution=allocate(mean,cov,method,settings,reversed_views)
                sleeve=solution.weights.to_numpy()
                scale=min(1.,settings.target_vol/solution.diagnostics["predicted_vol"])
                weights=sleeve*scale
                record.update(solution.diagnostics,status="ok",shrinkage=shrinkage,
                              risk_scale=scale,predicted_target_vol=solution.diagnostics["predicted_vol"]*scale)
                _,fractions=risk_contributions(sleeve,cov.to_numpy())
                record.update({"risk_fraction_"+a:float(fractions[j]) for j,a in enumerate(ASSETS)})
                snapshot={"variant":name,"decision_date":str(date.date()),"assets":list(ASSETS),
                          "annual_mean":mean.to_list(),"annual_covariance":cov.to_numpy().tolist(),
                          "effective_mean":solution.expected_returns.to_list(),"sleeve":sleeve.tolist(),
                          "target":weights.tolist(),"diagnostics":solution.diagnostics}
                if name in METHODS:base_solutions[name]=(solution,weights.copy())
            except (ValueError,FloatingPointError,ArithmeticError,np.linalg.LinAlgError,RuntimeError) as error:
                record["reason"]=f"{type(error).__name__}: {error}"
            schedules[name].append({"date":date,**{a:float(weights[j]) for j,a in enumerate(ASSETS)}})
            diagnostics.append(record)
            if snapshot is not None:snapshots.append(snapshot)
        if perturb and (cfg.lookback,cfg.covariance) in cache:
            mean,cov,_=cache[(cfg.lookback,cfg.covariance)]
            # A fixed stress magnitude under an IID approximation, not a confidence interval.
            standard_error=np.sqrt(252*np.diag(cov)/cfg.lookback)
            rng=np.random.default_rng(cfg.seed+date.toordinal())
            for draw in range(cfg.perturbations):
                noise=rng.normal(size=len(ASSETS))*standard_error
                for method in METHODS:
                    row={"decision_date":str(date.date()),"method":method,"draw":draw,
                         "status":"failed","reason":"","sleeve_half_l1":np.nan,"target_half_l1":np.nan,
                         **{"mean_shock_"+a:float(noise[j]) for j,a in enumerate(ASSETS)}}
                    if method not in base_solutions:
                        row["reason"]="Baseline solution unavailable";shocks.append(row);continue
                    original,original_target=base_solutions[method]
                    try:
                        alternative=allocate(mean+noise,cov,method,cfg) if method in {"mean_variance","black_litterman","return_tilted_budget"} else original
                        w=alternative.weights.to_numpy()
                        target=w*min(1.,cfg.target_vol/alternative.diagnostics["predicted_vol"])
                        row.update(status="ok",sleeve_half_l1=float(np.abs(w-original.weights.to_numpy()).sum()/2),
                                   target_half_l1=float(np.abs(target-original_target).sum()/2),
                                   optimality_residual=alternative.diagnostics["optimality_residual"],
                                   **{"target_"+a:float(target[j]) for j,a in enumerate(ASSETS)})
                    except (ValueError,FloatingPointError,ArithmeticError,np.linalg.LinAlgError,RuntimeError) as error:
                        row["reason"]=f"{type(error).__name__}: {error}"
                    shocks.append(row)
    tables={name:pd.DataFrame(rows).set_index("date") for name,rows in schedules.items()}
    return tables,pd.DataFrame(diagnostics),snapshots,pd.DataFrame(shocks)
