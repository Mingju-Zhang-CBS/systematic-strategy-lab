"""Predetermined synthetic controls and deliberately failed funding paths."""

from dataclasses import replace

import pandas as pd

from .engine import Protocol, run, validate
from .fixture import frames


def write_scenarios(output, protocol=Protocol()):
    summaries = []
    scenarios = [("base", protocol), ("zero_friction", replace(protocol, commission=0, slippage_ticks=0)),
                 ("zero_ticks", replace(protocol, slippage_ticks=0)),
                 ("two_ticks", replace(protocol, slippage_ticks=2)),
                 ("reserve_20pct", replace(protocol, reserve_rate=.2)),
                 ("buffer_10_sessions", replace(protocol, exit_buffer=10))]
    for name in ("negative_price", "capacity_rejection", "missing_reference", "safe_exit_failure", "insolvency", "unverified_calendar"):
        scenarios.append((name, protocol))
    for name, p in scenarios:
        q, c, k, m, start, end = frames()
        if name in {"negative_price", "capacity_rejection", "missing_reference", "safe_exit_failure", "insolvency", "unverified_calendar"}:
            c = c[c["product"] == "WTI"].copy()
            q = q[q["contract"].isin(c.contract)].copy()
            k = k[k["product"] == "WTI"].copy()
            dates = pd.to_datetime(k.session)
            if name == "safe_exit_failure":
                start, end = dates.iloc[160], dates.iloc[165]
                q.loc[(q.contract == c.contract.iloc[0]) & (q.session == str(dates.iloc[163].date())), "settlement"] = float("nan")
            else:
                start, end = dates.iloc[132], dates.iloc[135]
                if name in {"negative_price", "insolvency"}:
                    q.loc[(q.contract == c.contract.iloc[0]) & (q.session == str(dates.iloc[133].date())), "settlement"] = -5 if name == "negative_price" else -2000
                elif name == "capacity_rejection":
                    q["volume"] = 50
                elif name == "missing_reference":
                    q.loc[q.session == str(start.date()), "settlement"] = float("nan")
                else:
                    k["verified"] = False
        r = run(validate(q, c, k, m, start, end, p), p)
        folder = output / name
        folder.mkdir(parents=True)
        for key in ("ledger", "events", "decisions", "trades", "holdings", "selections"):
            r[key].to_csv(folder / (key+".csv"), index=False, lineterminator="\n")
        summaries.append(dict(scenario=name, data_kind="synthetic", status=r["status"],
                              products=c["product"].nunique(), recorded_days=len(r["ledger"]),
                              executed_legs=len(r["trades"]),
                              costs=0 if r["trades"].empty else r["trades"].total_cost.sum(),
                              ending_equity=None if r["ledger"].empty else r["ledger"].equity.iloc[-1],
                              events=len(r["events"])))
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / "scenario-summary.csv", index=False, lineterminator="\n")
    return summary
