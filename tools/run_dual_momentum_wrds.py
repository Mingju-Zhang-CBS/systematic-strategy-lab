"""Run the fixed-universe study in WRDS Cloud and save results privately."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from strategy_lab import dual_momentum as dm

INPUT_START = "2007-05-31"
INPUT_END = "2026-06-30"
RUN_ID = "dual-momentum-crsp-v1-20261109"
REM_ID = 92061


def query(db):
    tickers = ", ".join(repr(x) for x in dm.ASSETS)
    ids = db.raw_sql(f"""
        select distinct ticker, permno
        from crsp_q_stock.stksecurityinfohist
        where ticker in ({tickers})
          and secinfostartdt <= '{INPUT_START}' and secinfoenddt >= '{INPUT_START}'
          and securityenddt >= '{INPUT_END}'
        order by ticker, permno
    """)
    if len(ids) != 8 or set(ids.ticker) != set(dm.ASSETS) or not ids.permno.is_unique:
        raise ValueError("Historical mapping is missing or ambiguous")
    if ids.loc[ids.ticker.eq("REM"), "permno"].item() != REM_ID:
        raise ValueError("REM did not resolve to the homework's ETF")
    selected = ", ".join(str(int(x)) for x in ids.permno)
    daily = db.raw_sql(f"""
        select permno, dlycaldt, dlyprevdt, dlyret, dlyretx, dlyclose, dlyprcflg, dlydelflg
        from crsp_q_stock.dsf_v2 where permno in ({selected})
          and dlycaldt between '{INPUT_START}' and '{INPUT_END}'
        order by dlycaldt, permno
    """, date_cols=["dlycaldt", "dlyprevdt"])
    monthly = db.raw_sql(f"""
        select permno, mthcaldt, mthret from crsp_q_stock.msf_v2
        where permno in ({selected}) and mthcaldt between '2007-06-01' and '{INPUT_END}'
        order by mthcaldt, permno
    """, date_cols=["mthcaldt"])
    dist = db.raw_sql(f"""
        select disexdt, disdivamt from crsp_q_stock.stkdistributions
        where permno = {REM_ID} and disexdt between '2020-03-01' and '2020-03-31'
        order by disexdt, disseqnbr
    """, date_cols=["disexdt"])
    calendar = db.raw_sql(f"""
        select caldt from crsp_q_stock.metaexchangecalendar where tradingflg = 'Y'
          and caldt between '{INPUT_START}' and '{INPUT_END}' order by caldt
    """, date_cols=["caldt"])
    return ids, daily, monthly, dist, pd.DatetimeIndex(calendar.caldt)


def validate(ids, daily, monthly, calendar):
    if not calendar.is_unique or calendar[0] != pd.Timestamp(INPUT_START) or calendar[-1] != pd.Timestamp(INPUT_END):
        raise ValueError("Calendar does not cover both sample endpoints")
    labeled = daily.merge(ids, on="permno", validate="many_to_one")
    rets = labeled.pivot(index="dlycaldt", columns="ticker", values="dlyret").loc[:, list(dm.ASSETS)]
    if not rets.index.equals(calendar) or not np.isfinite(rets).all().all():
        raise ValueError("Missing session or non-finite ETF return")
    prev = labeled.pivot(index="dlycaldt", columns="ticker", values="dlyprevdt").reindex(calendar)
    if not prev.iloc[1:].eq(pd.Series(calendar[:-1], index=calendar[1:]), axis=0).all().all():
        raise ValueError("Non-consecutive CRSP return span")
    if not labeled.dlydelflg.eq("N").all():
        raise ValueError("ETF delisting requires a separate settlement policy")
    trade_closes = labeled.assign(close=labeled.dlyclose.where(labeled.dlyprcflg.eq("TR")))
    closes = trade_closes.pivot(index="dlycaldt", columns="ticker", values="close")
    formation = dm.monthly_marks(rets.iloc[1:])
    months = pd.period_range("2007-06", dm.END, freq="M")
    if not formation.index.equals(months):
        raise ValueError("Incomplete formation months")
    reference = monthly.assign(month=monthly.mthcaldt.dt.to_period("M")).merge(ids, on="permno", validate="many_to_one")
    reference = reference.pivot(index="month", columns="ticker", values="mthret").reindex_like(formation)
    if not np.isfinite(reference).all().all():
        raise ValueError("Incomplete CRSP monthly comparison")
    gap = formation.sub(reference).abs().stack()
    audit = {
        "daily_sessions_with_anchor": len(calendar),
        "daily_rows": len(daily),
        "monthly_comparisons": int(gap.size),
        "max_daily_vs_monthly_bps": float(gap.max() * 10_000),
        "p99_daily_vs_monthly_bps": float(gap.quantile(0.99) * 10_000),
        "comparisons_over_1bp": int(gap.gt(0.0001).sum()),
        "nontrade_close_rows": int(trade_closes.close.isna().sum()),
        "nontrade_close_rows_evaluation": int(trade_closes.loc[trade_closes.dlycaldt.ge("2012-01-01"), "close"].isna().sum()),
    }
    return rets.iloc[1:], closes, formation, audit


def rem_diagnostic(daily, monthly, distributions, yahoo):
    """Compare two ex-date reinvestment conventions without exposing source rows."""
    rem = daily.loc[daily.permno.eq(REM_ID)].set_index("dlycaldt").sort_index()
    march = rem.loc["2020-03"]
    close_move = march.dlyclose.iloc[-1] / rem.loc["2020-02", "dlyclose"].iloc[-1] - 1
    compounded = (1 + march.dlyret).prod() - 1
    ex_compounded = (1 + march.dlyretx).prod() - 1
    reference = monthly.loc[
        monthly.permno.eq(REM_ID) & monthly.mthcaldt.eq(pd.Timestamp("2020-03-31")), "mthret"
    ].item()
    if len(distributions) != 1:
        raise ValueError("Expected one REM distribution in March 2020")
    distribution = distributions.iloc[0]
    ex_date = distribution.disexdt
    crsp_amount = float(distribution.disdivamt)
    prev_close = rem.dlyclose.shift(1).loc[ex_date]
    ex_close = rem.at[ex_date, "dlyclose"]
    reinvest_ex_close = (1 + close_move) * (1 + crsp_amount / ex_close) - 1
    prior_close_adjustment = (1 + yahoo["price_return"]) * prev_close / (prev_close - yahoo["distribution"]) - 1
    return {
        "same_ex_date": ex_date == pd.Timestamp(yahoo["ex_date"]),
        "distribution_difference_under_0_001_usd": abs(crsp_amount - yahoo["distribution"]) < 0.001,
        "crsp_minus_archive_total_bps": float((compounded - yahoo["total_return"]) * 10_000),
        "close_move_difference_bps": float((close_move - yahoo["price_return"]) * 10_000),
        "daily_minus_monthly_total_bps": float((compounded - reference) * 10_000),
        "crsp_ex_distribution_minus_close_bps": float((ex_compounded - close_move) * 10_000),
        "crsp_ex_close_formula_residual_bps": float((compounded - reinvest_ex_close) * 10_000),
        "archive_prior_close_formula_residual_bps": float((yahoo["total_return"] - prior_close_adjustment) * 10_000),
    }


def run(db, rf_path, output, yahoo_path=None):
    rf = pd.read_csv(rf_path, index_col="month")["RF"]
    rf.index = pd.PeriodIndex(rf.index, freq="M")
    ids, daily, monthly, dist, calendar = query(db)
    rets, closes, formation, audit = validate(ids, daily, monthly, calendar)
    if yahoo_path:
        audit["rem"] = rem_diagnostic(daily, monthly, dist, json.loads(yahoo_path.read_text(encoding="utf-8")))
    all_returns = dm.session_returns(rets, rf)
    if not np.allclose(dm.monthly_marks(all_returns)["RF"], rf.reindex(formation.index), atol=1e-12):
        raise ArithmeticError("Cash return reconstruction failed")
    targets = dm.target_weights(formation.assign(RF=rf.reindex(formation.index)))
    base_signal_months = pd.period_range(dm.START, dm.END, freq="M") - 1
    if not np.allclose(targets["dual"].loc[base_signal_months, "RF"], targets["same_gate_equal"].loc[base_signal_months, "RF"]):
        raise ArithmeticError("Same-gate exposure failed")
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "run_id": RUN_ID,
        "sample": [dm.START, dm.END],
        "model_sha256": sha256(Path(dm.__file__).read_bytes()).hexdigest(),
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "rf_sha256": sha256(rf_path.read_bytes()).hexdigest(),
        "crsp_daily_fingerprint": sha256(pd.util.hash_pandas_object(daily, index=False).to_numpy().tobytes()).hexdigest(),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "audit": audit,
        "metrics": {},
        "paired_at_10bps": {},
    }
    baseline = {}
    for cost in dm.COSTS_BPS:
        result["metrics"][cost] = {}
        for arm in dm.ARMS:
            ledger = dm.simulate(all_returns, closes, targets[arm], cost)
            ledger.to_csv(output / f"{arm}_{cost}bps_daily.csv", index_label="session")
            result["metrics"][cost][arm] = dm.metrics(ledger, rf)
            if cost == 10:
                baseline[arm] = dm.monthly_marks(ledger["return"])
    for arm in dm.ARMS:
        if arm != "dual":
            result["paired_at_10bps"][arm] = dm.paired_log_growth(baseline["dual"], baseline[arm])
    months = pd.DataFrame(baseline)
    months.to_csv(output / "monthly_net_10bps.csv", index_label="month")
    annual = (1 + months).groupby(months.index.year).prod() - 1
    annual.to_csv(output / "calendar_year_net_10bps.csv", index_label="year")
    result["months"] = len(months)
    result["sessions"] = len(ledger)
    result["dual_years_ahead_10bps"] = {
        arm: int(annual.dual.gt(annual[arm]).sum()) for arm in dm.ARMS if arm != "dual"
    }
    result["year_periods"] = len(annual)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    import wrds

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rf", type=Path, required=True, help="Private CSV with month (YYYY-MM) and RF (decimal)")
    parser.add_argument("--out", type=Path, required=True, help="Private directory for ledgers and summary")
    parser.add_argument("--rem-reference", type=Path, help="Private JSON with price_return, total_return, ex_date and distribution")
    args = parser.parse_args()
    db = wrds.Connection()
    try:
        result = run(db, args.rf, args.out, args.rem_reference)
        print(f"Saved {result['run_id']} with {result['months']} evaluation months to the private output directory.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
