"""Paired partial retirement under known capacities, on invented curves only."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.engine import PRODUCTS
from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol, run_research
from strategy_lab.commodities.research_fixture import research_frames


@pytest.fixture(scope="module")
def panel():
    return prepare(*research_frames())


def retiring_tape(panel, spread=False):
    tape = deepcopy(panel)
    day = tape.dates.get_loc("2021-01-04")
    j = PRODUCTS.index("WTI")
    old = tape.pairs[day, j].copy()
    third = tape.contracts.index[tape.contracts.contract.eq("SYN_RESEARCH_WTI_2")][0]
    tape.pairs[day+1:day+12, j] = [old[1], third]
    if spread:
        for frame in tape.updates.values():
            frame["bm_spread_near_direction"] = 1
    protocol = ResearchProtocol(start="2021-01-04", end="2021-01-07", execution_policy="staged")
    return tape, protocol, day, j, old, third


def test_partial_outright_goal_survives_request_reversal(panel):
    tape, p, day, j, old, _ = retiring_tape(panel)
    tape.volume[day-1:day+8, old[0]] = 200
    tape.pairs[day+2, j] = old  # a changed request must not cancel pending retirement
    r = run_research(tape, "long_only", p)
    held = r["holdings"].query("product == 'WTI'")
    old_rows = held[held.contract == tape.contracts.contract.iloc[old[0]]]
    assert old_rows.quantity.tolist() == [6, 4, 2]
    assert held.query("session == '2021-01-07'").contract.tolist() == [tape.contracts.contract.iloc[old[1]]]
    slices = r["exit_plans"].query("product == 'WTI'")
    assert slices.planned_units.tolist() == [2, 2, 2]
    assert slices.goal_units.eq(0).all()
    assert r["events"].query("product == 'WTI'").code.eq("entry_blocked_by_pending_reduction").sum() == 2
    assert abs(r["reconciliation"]["terminal_error"]) < 1e-6


def test_spread_slice_uses_smaller_leg_and_preserves_pairing(panel):
    tape, p, day, _, old, _ = retiring_tape(panel, True)
    initial = run_research(tape, "bm_spread", replace(p, end=p.start))
    quantity = int(initial["holdings"].query("product == 'WTI'").quantity.abs().max())
    assert quantity >= 2
    cap = max(1, quantity//2)
    tape.volume[day-1, old[0]] = 50_000
    tape.volume[day-1, old[1]] = cap/p.participation
    result = run_research(tape, "bm_spread", replace(p, end="2021-01-05"))
    held = result["holdings"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(held) == 2 and held.quantity.sum() == 0
    assert held.quantity.abs().eq(quantity-cap).all()
    fills = result["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(fills) == 2 and fills.delta.sum() == 0
    assert fills.delta.abs().eq(cap).all()
    assert fills.cost.sum() > 0
    np.testing.assert_allclose(result["ledger"].equity, result["ledger"].opening_equity+result["ledger"].variation_margin-result["ledger"].costs)


def test_missing_leg_reference_rejects_entire_planned_slice(panel):
    tape, p, day, _, old, _ = retiring_tape(panel, True)
    tape.volume[day-1, old[1]] = 100
    tape.prices[day+1, old[1]] = np.nan
    r = run_research(tape, "bm_spread", replace(p, end="2021-01-05"))
    assert r["trades"].query("session == '2021-01-05' and product == 'WTI'").empty
    previous = r["holdings"].query("session == '2021-01-04' and product == 'WTI'").set_index("contract").quantity
    current = r["holdings"].query("session == '2021-01-05' and product == 'WTI'").set_index("contract").quantity
    pd.testing.assert_series_equal(previous, current)
    assert r["events"].detail.eq("missing_execution_reference").any()


def test_zero_capacity_at_deadline_still_fails_without_phantom_fill(panel):
    tape, p, day, _, old, _ = retiring_tape(panel)
    tape.deadlines[old[0]] = day+1
    tape.volume[day-1, old[0]] = 0
    r = run_research(tape, "long_only", replace(p, end="2021-01-05", exit_lead=10))
    assert r["status"] == "failed_known_boundary_exit"
    assert r["trades"].query("session == '2021-01-05' and product == 'WTI'").empty
    assert r["exit_plans"].query("product == 'WTI'").planned_units.eq(0).all()


def test_early_lead_retires_then_locks_out_same_maturity(panel):
    tape, p, day, j, old, third = retiring_tape(panel)
    tape.pairs[day+1:day+4, j] = old
    tape.pairs[day+4:day+12, j] = [old[1], third]
    tape.deadlines[old[0]] = day+8
    r = run_research(tape, "long_only", replace(p, end="2021-01-11", exit_lead=10))
    held = r["holdings"].query("product == 'WTI'")
    assert held[held.session.between("2021-01-05", "2021-01-07")].empty
    assert not held.query("session >= '2021-01-08'").empty
    assert held.query("session >= '2021-01-08'").contract.eq(tape.contracts.contract.iloc[old[1]]).all()
    assert r["events"].query("product == 'WTI'").code.eq("early_retirement_started").sum() == 1


def test_missing_trailing_capacity_triggers_early_without_using_today(panel):
    tape, p, day, j, old, _ = retiring_tape(panel)
    tape.pairs[day+1:day+12, j] = old
    tape.deadlines[old[0]] = day+60
    tape.volume[day-1, old[0]] = 0
    r = run_research(tape, "long_only", replace(p, exit_lead=10))
    plan = r["exit_plans"].query("session == '2021-01-05' and product == 'WTI'").iloc[0]
    assert plan.remaining_sessions > 10
    assert plan.early_retirement and plan.planned_units == 0
    assert tape.volume[day+1, old[0]] > 0  # execution-day liquidity cannot increase the frozen slice


def test_execution_price_cannot_resize_planned_partial_slice(panel):
    tape, p, day, _, old, _ = retiring_tape(panel)
    tape.volume[day-1, old[0]] = 200
    changed = deepcopy(tape)
    changed.prices[day+1] *= 3
    config = replace(p, end="2021-01-05")
    a, b = run_research(tape, "long_only", config), run_research(changed, "long_only", config)
    pd.testing.assert_frame_equal(a["exit_plans"], b["exit_plans"])
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])


def test_nonzero_drain_budget_can_trigger_before_fixed_lead(panel):
    tape, p, day, j, old, _ = retiring_tape(panel)
    p = replace(p, capital=3_000_000, exit_lead=10, end="2021-01-05")
    initial = run_research(tape, "long_only", replace(p, end=p.start))
    units = int(initial["holdings"].query("product == 'WTI'").quantity.iloc[0])
    assert units > 12
    tape.pairs[day+1:day+12, j] = old
    tape.deadlines[old[0]] = day+units-2
    tape.volume[day-1, old[0]] = 100
    r = run_research(tape, "long_only", p)
    plan = r["exit_plans"].query("product == 'WTI'").iloc[0]
    assert plan.remaining_sessions > p.exit_lead
    assert plan.conservative_capacity == 1 and plan.early_retirement
    assert plan.planned_units == 1


def test_final_spread_slice_cannot_reuse_overlap_capacity(panel):
    tape, p, day, _, old, _ = retiring_tape(panel, True)
    initial = run_research(tape, "bm_spread", replace(p, end=p.start))
    units = int(initial["holdings"].query("product == 'WTI'").quantity.abs().max())
    tape.volume[day-1, old[1]] = units/p.participation
    r = run_research(tape, "bm_spread", replace(p, end="2021-01-05"))
    assert r["holdings"].query("session == '2021-01-05' and product == 'WTI'").empty
    trades = r["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(trades) == 2 and trades.delta.sum() == 0
    assert r["events"].query("session == '2021-01-05' and product == 'WTI'").code.eq("unfilled_open_basket").any()


def test_future_data_cannot_change_prior_retirement_state(panel):
    tape, p, day, _, old, _ = retiring_tape(panel)
    tape.volume[day-1:day+10, old[0]] = 200
    changed = deepcopy(tape)
    future = changed.dates > pd.Timestamp(p.end)
    changed.prices[future] *= 4
    changed.volume[future] = 0
    a, b = run_research(tape, "long_only", p), run_research(changed, "long_only", p)
    for name in ("decisions", "exit_plans", "ledger", "trades"):
        pd.testing.assert_frame_equal(a[name], b[name])
