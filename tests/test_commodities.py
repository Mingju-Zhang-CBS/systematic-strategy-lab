"""Economic invariants and information-clock probes; all inputs are synthetic."""

from dataclasses import replace
import os
import subprocess
import sys
from io import StringIO

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.engine import Protocol, run, validate
from strategy_lab.commodities.fixture import frames


def single(product="WTI", days=4, offset=0):
    q, c, k, m, start, end = frames()
    c = c[c["product"] == product].copy()
    q = q[q["contract"].isin(c["contract"])].copy()
    k = k[k["product"] == product].copy()
    dates = pd.to_datetime(k["session"])
    start = dates.iloc[132+offset]
    end = dates.iloc[132+offset+days-1]
    return q, c, k, m, start, end


@pytest.fixture(scope="module")
def eight_result():
    return run(validate(*frames()))


def test_eight_products_and_cash_conservation(eight_result):
    r = eight_result
    assert r["status"] == "completed_accounting_diagnostic"
    assert r["trades"]["product"].nunique() == 8
    l = r["ledger"]
    np.testing.assert_allclose(l.equity, l.opening_equity + l.variation_margin - l.costs, atol=1e-8)
    np.testing.assert_allclose(l.opening_equity.iloc[1:], l.equity.iloc[:-1], atol=1e-8)
    assert l.costs.sum() == pytest.approx(r["trades"].total_cost.sum())


def test_model_margin_encumbers_without_double_expense(eight_result):
    l = eight_result["ledger"]
    np.testing.assert_allclose(l.reserve, .1*l.gross_proxy)
    np.testing.assert_allclose(l.free_cash, l.equity-l.reserve)
    assert (l.reserve <= .5*l.equity).all()
    assert (l.gross_proxy <= 3*l.equity).all()


def test_pair_integer_quantity_and_roll_costs(eight_result):
    h = eight_result["holdings"]
    for _, g in h.groupby(["session", "product"]):
        assert len(g) == 2 and g.quantity.sum() == 0
        assert np.equal(g.quantity, np.trunc(g.quantity)).all()
    t = eight_result["trades"]
    assert t.contract.nunique() > 16  # rolls occurred in all eight products
    assert (t.total_cost == t.commission + t.slippage).all()
    assert (t.commission == t.delta.abs()*2.5).all()


def test_ticks_and_cents(eight_result):
    t = eight_result["trades"]
    assert (t[t["product"] == "SILVER"].slippage / t[t["product"] == "SILVER"].delta.abs() == 25).all()
    corn = t[t["product"] == "CORN"]
    assert corn.settlement_reference.between(3, 6).all()
    assert (corn.slippage / corn.delta.abs() == 12.5).all()


def test_no_same_day_information(eight_result):
    d = eight_result["decisions"]
    assert (pd.to_datetime(d.available_at, utc=True) <= pd.to_datetime(d.decision_at, utc=True)).all()
    assert (pd.to_datetime(d.observation) < pd.to_datetime(d.session)).all()


def test_future_price_volume_and_metadata_do_not_change_past_decisions():
    values = list(single(days=6))
    baseline = run(validate(*values))
    q, c = values[0].copy(), values[1].copy()
    future = q["session"] > str(values[-2].date())
    q.loc[future, "settlement"] *= 4
    q.loc[future, "volume"] = 0
    revision = c.copy()
    revision["known_at"] = "2025-12-01T00:00:00+00:00"
    revision["delivery"] = "2026-12-01"
    values[0], values[1] = q, pd.concat([c, revision], ignore_index=True)
    changed = run(validate(*values))
    day = str(values[-2].date())
    pd.testing.assert_frame_equal(baseline["decisions"].query("session == @day"), changed["decisions"].query("session == @day"))


def test_execution_price_changes_ledger_not_frozen_target():
    values = list(single(days=1))
    a = run(validate(*values))
    values[0].loc[values[0]["session"] == str(values[-2].date()), "settlement"] += .05
    b = run(validate(*values))
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])
    assert a["trades"].settlement_reference.iloc[0] != b["trades"].settlement_reference.iloc[0]


def test_roll_gap_not_credited_as_pnl():
    values = list(single(days=23, offset=20))
    for n, key in enumerate(values[1].contract):
        values[0].loc[values[0].contract == key, "settlement"] = 70 + 20*n
    r = run(validate(*values))
    assert r["trades"].contract.nunique() >= 3
    assert r["ledger"].variation_margin.eq(0).all()
    assert r["ledger"].equity.iloc[-1] == pytest.approx(1e6-r["trades"].total_cost.sum())


def test_safe_exit_failure_is_not_dropped():
    values = list(single(days=5, offset=29))  # safe exit index 163
    key = values[1].contract.iloc[0]
    deadline = pd.to_datetime(values[2].session).iloc[163]
    values[0].loc[(values[0].contract == key) & (values[0].session == str(deadline.date())), "settlement"] = np.nan
    r = run(validate(*values))
    assert r["status"] == "failed_safe_exit"
    assert "stale_mark" in r["events"].code.values
    assert "unfilled_basket" in r["events"].code.values
    last_day = r["ledger"].iloc[-1]["session"]
    assert key in r["holdings"].query("session == @last_day").contract.values
    assert r["ledger"].iloc[-1].stale_contracts == 1


def test_negative_settlement_preserved_in_dollar_pnl():
    values = list(single(days=2))
    key = values[1].contract.iloc[0]
    date = str(pd.to_datetime(values[2].session).iloc[133].date())
    values[0].loc[(values[0].contract == key) & (values[0].session == date), "settlement"] = -37.63
    r = run(validate(*values))
    assert r["holdings"].mark.min() == -37.63
    assert r["ledger"].variation_margin.min() < -100000
    assert np.isfinite(r["ledger"].equity).all()


def test_no_refunding_after_insolvency():
    values = list(single(days=5))
    key = values[1].contract.iloc[0]
    date = str(pd.to_datetime(values[2].session).iloc[133].date())
    values[0].loc[(values[0].contract == key) & (values[0].session == date), "settlement"] = -2000
    r = run(validate(*values))
    assert r["status"] == "failed_nonpositive_equity"
    assert len(r["ledger"]) == 2
    assert r["ledger"].iloc[-1].equity <= 0


def test_zero_lagged_volume_and_future_listing_excluded():
    values = list(single(days=1))
    c, q = values[1], values[0]
    q.loc[q.contract == c.contract.iloc[0], "volume"] = 0
    c.loc[c.index[1], "listed_at"] = "2026-01-01T00:00:00+00:00"
    r = run(validate(*values))
    assert {"lagged_activity_or_price_failure", "not_yet_listed"} <= set(r["selections"].reason)
    assert not set(c.contract.iloc[:2]) & set(r["trades"].contract)


def test_lagged_capacity_rejects_whole_pair():
    values = list(single(days=1))
    values[0]["volume"] = 50
    r = run(validate(*values))
    assert r["trades"].empty
    assert "lagged_participation_limit" in r["events"].detail.values


def test_unverified_evidence_is_quarantined():
    values = list(single(days=2))
    values[1]["boundary_verified"] = False
    r = run(validate(*values))
    assert r["trades"].empty
    assert r["selections"].reason.eq("unverified_contract_evidence").all()
    assert r["events"].code.eq("no_qualified_pair").all()


def test_margin_shortfall_rejects_integer_pair():
    p = replace(Protocol(), capital=100)
    r = run(validate(*single(days=1), p), p)
    assert r["trades"].empty
    assert "integer_risk_or_funding_rejection" in r["events"].code.values
    for table in ("ledger", "trades", "decisions", "selections", "holdings", "events"):
        restored = pd.read_csv(StringIO(r[table].to_csv(index=False)))
        assert list(restored.columns) == list(r[table].columns)


def test_risk_history_is_required():
    values = list(single(days=1))
    values[0] = values[0][values[0].session >= "2024-06-01"]
    r = run(validate(*values))
    assert r["trades"].empty
    assert "insufficient_risk_history" in r["events"].code.values


def test_post_mark_funding_cannot_resize_frozen_order():
    values = list(single(days=1))
    values[0].loc[values[0].session == str(values[-2].date()), "settlement"] = 1e7
    r = run(validate(*values))
    assert r["decisions"].target.abs().sum() == 2
    assert r["trades"].empty
    assert r["events"].detail.str.contains("post_mark_funding_limit").any()


def test_first_position_precedes_notice_in_safe_boundary():
    values = single(days=3, offset=30)
    r = run(validate(*values))
    key = values[1].contract.iloc[0]
    deadline = str(pd.to_datetime(values[2].session).iloc[163].date())
    excluded = r["selections"].query("contract == @key and session == @deadline")
    assert excluded.reason.iloc[0] == "inside_delivery_buffer"
    assert excluded.safe_exit.iloc[0] == deadline
    assert key not in r["holdings"].query("session == @deadline").contract.values


def test_calendar_closure_keeps_existing_position_without_fake_trade(eight_result):
    values = frames()
    calendar = values[2]
    dates = set(calendar[calendar["product"] == "CORN"].session)
    corn_trades = eight_result["trades"].query("product == 'CORN'")
    assert set(corn_trades.session) <= dates
    # Fixture has an actual differing closure, not a generic weekday assumption.
    assert dates != set(calendar[calendar["product"] == "WTI"].session)


def test_execution_zero_volume_rejects_without_changing_decision():
    values = list(single(days=1))
    a = run(validate(*values))
    values[0].loc[values[0].session == str(values[-2].date()), "volume"] = 0
    b = run(validate(*values))
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])
    assert b["trades"].empty
    assert "zero_or_missing_execution_activity" in b["events"].detail.values


def test_missing_notice_or_unverified_deadline_calendar_blocks_entry():
    values = list(single(days=1))
    values[1]["first_notice"] = None
    assert run(validate(*values))["trades"].empty
    values = list(single(days=1))
    # Future sessions used to compute a deadline must themselves have evidence.
    values[2].loc[pd.to_datetime(values[2].session) >= "2024-08-01", "verified"] = False
    assert run(validate(*values))["trades"].empty


def test_stale_mark_recovers_without_fabricated_fill():
    values = list(single(days=5))
    q, c, k = values[:3]
    key = c.contract.iloc[0]
    date = str(pd.to_datetime(k.session).iloc[133].date())
    q.loc[(q.contract == key) & (q.session == date), "settlement"] = np.nan
    r = run(validate(*values))
    assert r["ledger"].stale_contracts.max() == 1
    assert r["ledger"].iloc[-1].stale_contracts == 0
    assert "stale_mark" in r["events"].code.values
    np.testing.assert_allclose(r["ledger"].equity, r["ledger"].opening_equity + r["ledger"].variation_margin - r["ledger"].costs)


def test_held_unit_change_fails_instead_of_reinterpreting_pnl():
    values = list(single(days=4))
    version = values[1].copy()
    version["valid_from"] = str(pd.to_datetime(values[2].session).iloc[134].date())
    version["known_at"] = "2023-12-02T00:00:00+00:00"
    version["multiplier"] *= 10
    values[1] = pd.concat([values[1], version], ignore_index=True)
    r = run(validate(*values))
    assert r["status"] == "failed_held_contract_evidence"
    assert "held_contract_unit_change" in r["events"].code.values


def test_process_hash_seed_does_not_change_accounting_or_row_order():
    code = """from strategy_lab.commodities.fixture import frames
from strategy_lab.commodities.engine import validate,run
import hashlib,json
values=list(frames());values[-1]=values[-2]+__import__('pandas').Timedelta(days=5)
r=run(validate(*values))
print(json.dumps({k:hashlib.sha256(r[k].to_csv(index=False).encode()).hexdigest() for k in ('ledger','trades','decisions','holdings')}))
"""
    outputs = []
    for seed in ("1", "2"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        outputs.append(subprocess.run([sys.executable, "-c", code], env=env,
                                      capture_output=True, text=True, check=True).stdout)
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("failure", ["duplicate", "negative_volume", "naive_clock", "bad_scale", "unmapped_quote"])
def test_structural_input_errors_fail_at_boundary(failure):
    values = list(single(days=1))
    if failure == "duplicate":
        values[0] = pd.concat([values[0], values[0].iloc[:1]])
    elif failure == "negative_volume":
        values[0].iloc[0, values[0].columns.get_loc("volume")] = -1
    elif failure == "naive_clock":
        values[2]["decision_at"] = values[2].decision_at.str.replace("+00:00", "", regex=False)
    elif failure == "bad_scale":
        values[1]["usd_scale"] = 0
    else:
        values[0].iloc[0, values[0].columns.get_loc("contract")] = "UNKNOWN"
    with pytest.raises(ValueError):
        validate(*values)
