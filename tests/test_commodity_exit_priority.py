"""Order priority and lagged eligibility invariants on invented curves."""
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
def inputs():
    return research_frames()


@pytest.fixture(scope="module")
def panel(inputs):
    return prepare(*inputs)


def roll_case(panel, spread=False):
    tape = deepcopy(panel)
    first = tape.dates.get_loc("2021-01-04")
    product = PRODUCTS.index("WTI")
    old = tape.pairs[first, product].copy()
    third = tape.contracts.index[tape.contracts.contract == "SYN_RESEARCH_WTI_2"][0]
    tape.pairs[first+1, product] = [old[1], third]
    if spread:
        for score in tape.updates.values():
            score["bm_spread_near_direction"] = 1
    p = ResearchProtocol(start="2021-01-04", end="2021-01-05", execution_policy="exit_first")
    return tape, p, first, old, third


def test_rejected_replacement_cannot_prevent_feasible_old_close(panel):
    tape, p, day, old, _ = roll_case(panel)
    tape.volume[day-1, old[1]] = 0  # t-2 for the second decision
    tape.deadlines[old[0]] = day+1
    result = run_research(tape, "long_only", p)
    wti = result["holdings"].query("product == 'WTI'")
    assert len(wti.query("session == '2021-01-04'")) == 1
    assert wti.query("session == '2021-01-05'").empty
    assert result["status"] == "completed_exploratory_path"
    assert result["events"].code.eq("unfilled_open_basket").any()
    closed = result["trades"].query("product == 'WTI'")
    assert closed.delta.sum() == 0
    assert closed.cost.sum() > 0
    assert abs(result["reconciliation"]["terminal_error"]) < 1e-6
    legacy = run_research(tape, "long_only", replace(p, execution_policy="coupled"))
    assert legacy["status"] == "failed_known_boundary_exit"


def test_unfillable_exit_remains_failure_and_blocks_new_risk(panel):
    tape, p, day, old, _ = roll_case(panel)
    tape.volume[day-1, old[0]] = 0
    tape.deadlines[old[0]] = day+1
    result = run_research(tape, "long_only", p)
    assert result["status"] == "failed_known_boundary_exit"
    assert result["events"].code.eq("entry_blocked_by_unfilled_exit").any()
    assert result["holdings"].query("session == '2021-01-05' and product == 'WTI'").contract.tolist() == [tape.contracts.contract.iloc[old[0]]]


def test_spread_close_atomic_and_overlap_consumes_shared_capacity(panel):
    tape, p, day, old, _ = roll_case(panel, spread=True)
    ample = run_research(tape, "bm_spread", p)
    rollover = ample["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(rollover) == 4  # includes separately charged close/open overlap
    assert (rollover.cost > 0).all()
    routing = ample["events"].query("session == '2021-01-05'")
    reductions = routing.index[routing.code.eq("filled_reduce_basket")]
    additions = routing.index[routing.code.eq("filled_open_basket")]
    assert reductions.max() < additions.min()  # portfolio-wide priority
    initial = run_research(tape, "bm_spread", replace(p, end=p.start))
    held = initial["holdings"].query("product == 'WTI'")
    assert len(held) == 2
    quantity = int(held.quantity.abs().max())
    tape.volume[day-1, old[1]] = quantity / p.participation
    result = run_research(tape, "bm_spread", p)
    closes = result["trades"].query("session == '2021-01-05' and product == 'WTI'")
    assert len(closes) == 2
    assert closes.delta.sum() == 0
    assert result["holdings"].query("session == '2021-01-05' and product == 'WTI'").empty
    assert result["events"].query("product == 'WTI'").code.eq("unfilled_open_basket").any()
    # Inability to close either old leg leaves BOTH old legs untouched.
    tape.volume[day-1, old[0]] = 0
    failed = run_research(tape, "bm_spread", p)
    assert failed["trades"].query("session == '2021-01-05' and product == 'WTI'").empty
    assert len(failed["holdings"].query("session == '2021-01-05' and product == 'WTI'")) == 2


def test_five_observations_and_maturity_floors_are_causal(inputs):
    q, c, m = inputs
    q = q.copy()
    shock = pd.Timestamp("2020-06-15")
    q.loc[(q.contract == "SYN_RESEARCH_WTI_0") & (q.session == shock), "volume"] = 0
    tape = prepare(q, c, m, liquidity_window=5, monotone_roll=True)
    rows = tape.selection.query("product == 'WTI'").set_index("session")
    before = rows.loc["2020-06-16", "near"]
    after = rows.loc["2020-06-17", "near"]
    assert before == "SYN_RESEARCH_WTI_0"
    assert after == "SYN_RESEARCH_WTI_1"
    assert rows.loc["2020-07-01", "near"] == after
    delivery = c.set_index("contract").delivery
    for product, selected in tape.selection.query("near != ''").groupby("product"):
        for slot in ("near", "far"):
            assert (selected[slot].map(delivery).diff().dropna() >= pd.Timedelta(0)).all()
    future = q.copy()
    future.loc[future.session > "2021-06-30", ["volume", "open_interest"]] = 0
    changed = prepare(future, c, m, liquidity_window=5, monotone_roll=True)
    pd.testing.assert_frame_equal(tape.selection.query("session <= '2021-06-30'"), changed.selection.query("session <= '2021-06-30'"))
    p = ResearchProtocol(start="2021-01-04", end="2021-06-30", execution_policy="exit_first")
    a, b = run_research(tape, "carry", p), run_research(changed, "carry", p)
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])
    pd.testing.assert_frame_equal(a["ledger"], b["ledger"])


def test_liquidity_window_requires_every_lagged_observation(inputs):
    q, c, m = inputs
    q = q.copy()
    q.loc[(q.contract == "SYN_RESEARCH_WTI_0") & (q.session == "2020-06-15"), "open_interest"] = np.nan
    tape = prepare(q, c, m, liquidity_window=5)
    rows = tape.selection.query("product == 'WTI'").set_index("session")
    assert rows.loc["2020-06-16", "near"] == "SYN_RESEARCH_WTI_0"
    assert rows.loc["2020-06-17":"2020-06-23", "near"].eq("SYN_RESEARCH_WTI_1").all()
    assert rows.loc["2020-06-24", "near"] == "SYN_RESEARCH_WTI_0"


def test_unknown_execution_policy_rejected_at_entry(panel):
    with pytest.raises(ValueError, match="invalid research"):
        run_research(panel, "carry", ResearchProtocol(execution_policy="magic_fills"))
