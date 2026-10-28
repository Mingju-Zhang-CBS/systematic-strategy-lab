"""Economic and information invariants on invented curves, never real alpha."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.panel import prepare
from strategy_lab.commodities.research import ResearchProtocol, run_research
from strategy_lab.commodities.research_fixture import research_frames
from strategy_lab.commodities.scheduled import scheduled_sessions
from strategy_lab.commodities.research_report import paired_inference


@pytest.fixture(scope="module")
def inputs():
    return research_frames()


@pytest.fixture(scope="module")
def panel(inputs):
    return prepare(*inputs)


def test_declared_calendar_rules_are_not_observed_quote_dates():
    dates, closed = scheduled_sessions("2020-01-01", "2023-01-10")
    assert pd.Timestamp("2021-12-31") in dates
    assert pd.Timestamp("2021-06-18") in dates
    assert pd.Timestamp("2022-06-20") not in dates
    assert pd.Timestamp("2020-04-10") not in dates
    assert pd.Timestamp("2020-07-03") not in dates
    assert pd.Timestamp("2023-01-02") not in dates
    assert closed.evidence.str.contains("proxy").all()


def test_missing_front_notice_does_not_promote_distant_contracts(inputs):
    q, c, m = inputs
    c = c.copy()
    c.loc[c.contract == "SYN_RESEARCH_WTI_0", "first_notice"] = pd.NaT
    tape = prepare(q, c, m)
    rows = tape.selection.query("product == 'WTI' and session < '2021-05-01'")
    assert set(rows.reason) == {"front_notice_evidence_missing"}
    assert (rows.near == "").all()


def test_reference_return_does_not_include_delivery_price_gap(inputs):
    q, c, m = inputs
    q = q.copy()
    q["settlement"] = q.contract.map({key:100.+i*20 for i, key in enumerate(c.contract)})
    tape = prepare(q, c, m)
    valid = tape.monthly_returns.near_return.dropna()
    assert len(valid) > 0
    assert (valid == 0).all()


def test_grain_cents_and_negative_prices_are_preserved(inputs):
    q, c, m = inputs
    q = q.copy()
    key = "SYN_RESEARCH_CORN_0"
    dates = q.loc[q.contract == key, "session"].iloc[:2]
    q.loc[(q.contract == key) & (q.session == dates.iloc[0]), "settlement"] = 400.
    q.loc[(q.contract == key) & (q.session == dates.iloc[1]), "settlement"] = 401.
    q.loc[(q.contract == "SYN_RESEARCH_WTI_0") & (q.session == pd.Timestamp("2020-04-20")), "settlement"] = -37.63
    tape = prepare(q, c, m)
    column = tape.contracts.index[tape.contracts.contract == key][0]
    assert tape.deltas[tape.dates.get_loc(dates.iloc[1]), column] == pytest.approx(50)
    negative = tape.contracts.index[tape.contracts.contract == "SYN_RESEARCH_WTI_0"][0]
    assert tape.prices[tape.dates.get_loc("2020-04-20"), negative] == -37.63


def test_funded_cash_pairing_and_independent_terminal_bridge(panel):
    p = ResearchProtocol(start="2021-01-01", end="2021-12-31")
    r = run_research(panel, "bm_spread", p)
    assert r["status"] == "completed_exploratory_path"
    l = r["ledger"]
    np.testing.assert_allclose(l.equity, l.opening_equity+l.variation_margin-l.costs, atol=1e-8)
    np.testing.assert_allclose(l.reserve, p.reserve_rate*l.gross_proxy)
    assert abs(r["reconciliation"]["terminal_error"]) < 1e-6
    assert l.costs.sum() == pytest.approx(r["trades"].cost.sum())
    quantities = r["holdings"].groupby(["session", "product"]).quantity.agg(["sum", "size"])
    assert (quantities["sum"] == 0).all()
    assert (quantities["size"] == 2).all()


def test_future_quotes_cannot_change_past_requests_or_cash(inputs):
    q, c, m = inputs
    changed = q.copy()
    future = changed.session > pd.Timestamp("2021-06-30")
    changed.loc[future, "settlement"] *= 3
    changed.loc[future, "volume"] = 0
    p = ResearchProtocol(start="2021-01-01", end="2021-06-30")
    a = run_research(prepare(q, c, m), "carry", p)
    b = run_research(prepare(changed, c, m), "carry", p)
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])
    pd.testing.assert_frame_equal(a["ledger"], b["ledger"])


def test_execution_reference_does_not_resize_frozen_request(inputs):
    q, c, m = inputs
    changed = q.copy()
    changed.loc[changed.session == pd.Timestamp("2021-01-04"), "settlement"] *= 10
    p = ResearchProtocol(start="2021-01-04", end="2021-01-04")
    a = run_research(prepare(q, c, m), "long_only", p)
    b = run_research(prepare(changed, c, m), "long_only", p)
    pd.testing.assert_frame_equal(a["decisions"], b["decisions"])
    assert b["events"].detail.str.contains("funding").any()


def test_unfilled_delivery_exit_stops_funded_path(inputs, panel):
    q, c, m = inputs
    key = "SYN_RESEARCH_WTI_0"
    column = panel.contracts.index[panel.contracts.contract == key][0]
    deadline = panel.dates[panel.deadlines[column]]
    changed = q.copy()
    changed.loc[(changed.contract == key) & (changed.session == deadline), "volume"] = 0
    p = ResearchProtocol(start="2021-01-01", end="2021-06-01")
    r = run_research(prepare(changed, c, m), "long_only", p)
    assert r["status"] == "failed_known_boundary_exit"
    assert r["ledger"].session.iloc[-1] == str(deadline.date())
    assert r["events"].code.eq("failed_known_boundary_exit").any()


def test_low_capacity_rejection_is_retained(panel):
    p = ResearchProtocol(start="2021-01-04", end="2021-01-04", participation=.000001)
    r = run_research(panel, "long_only", p)
    assert r["status"] == "completed_no_qualified_trades"
    assert r["events"].detail.eq("lagged_participation_limit").any()
    assert r["ledger"].equity.iloc[-1] == p.capital


def test_bad_front_unit_interval_blocks_instead_of_promoting(inputs):
    q, c, m = inputs
    c = c.copy()
    bad = c.contract == "SYN_RESEARCH_WTI_0"
    c.loc[bad, "valid_to"] = "2017-01-01"
    c.loc[bad, "unit_evidence"] = False
    tape = prepare(q, c, m)
    rows = tape.selection.query("product == 'WTI' and session < '2021-05-01'")
    assert rows.reason.eq("front_specification_evidence_missing").all()


def inference_months():
    names = ["bm_outright", "bm_spread", "half_mix"]
    months = pd.period_range("2005-01", "2025-12", freq="M").astype(str)
    return {name:pd.DataFrame(dict(month=months, return_=-.01 if name == "bm_outright" else 0.,
                                   valid=True, exposed_sessions=1)) for name in names}


def test_paired_inference_retains_negative_effect_and_holm_family():
    table = paired_inference(inference_months())
    negative = table[table.claim == "bm_increment"]
    assert (negative["mean"] < 0).all()
    np.testing.assert_allclose(negative["mean"], -.01)
    assert (negative.holm_p >= negative.p_value).all()
    zero = table[table.claim == "bm_spread_mean"]
    assert zero.p_value.eq(1).all()
    pd.testing.assert_frame_equal(table, paired_inference(inference_months()))


def test_inference_does_not_silently_drop_an_invalid_month():
    months = inference_months()
    months["bm_outright"].loc[months["bm_outright"].month == "2021-04", "valid"] = False
    out = paired_inference(months)
    selected = out[(out.phase == "confirmation") & (out.claim == "bm_increment")]
    assert selected.status.eq("not_evaluable_incomplete_or_failed_months").all()
    assert selected.p_value.isna().all()


def test_no_funded_exposure_is_not_reported_as_zero_alpha_evidence():
    months = inference_months()
    months["bm_spread"]["exposed_sessions"] = 0
    out = paired_inference(months)
    assert out[out.claim == "bm_spread_mean"].status.eq("not_evaluable_no_BM_exposure").all()


def test_t_minus_two_never_indexes_the_end_of_a_short_input(panel):
    with pytest.raises(ValueError, match="two preceding"):
        run_research(panel, "long_only", ResearchProtocol(start="2019-01-02", end="2019-01-04"))
