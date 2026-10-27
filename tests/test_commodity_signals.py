"""Synthetic hypotheses only; these tests certify no historical data source."""

import numpy as np
import pandas as pd
import pytest

from strategy_lab.commodities.engine import PRODUCTS
from strategy_lab.commodities.signals import monthly_candidates


def monthly_frames():
    returns, curves = [], []
    for j, product in enumerate(PRODUCTS):
        for month in pd.period_range("2023-01", "2024-02", freq="M"):
            available = (month+1).start_time.tz_localize("UTC")+pd.Timedelta(days=1)
            returns.append(dict(product=product, month=str(month), near_return=.001*(j+1),
                                far_return=.001, available_at=available.isoformat()))
        curves.append(dict(product=product, month="2023-12", near_price=100.+j, far_price=102.,
                           near_delivery="2024-03-01", far_delivery="2024-06-01",
                           eligible=True, available_at="2024-01-02T00:00:00+00:00"))
    return pd.DataFrame(returns), pd.DataFrame(curves)


def calculate(r, c):
    return monthly_candidates(r, c, "2023-12", "2024-01-03T14:00:00+00:00").set_index("product")


def test_compounded_return_difference_and_carry_units():
    r, c = monthly_frames()
    out = calculate(r, c)
    assert out.loc["WTI", "basis_momentum"] == pytest.approx(0)
    assert out.loc["SOYBEANS", "basis_momentum"] == pytest.approx(1.008**12-1.001**12)
    assert out.loc["WTI", "carry"] == pytest.approx(np.log(100/102)*365/92)
    assert (out.bm_spread_near_direction == -out.bm_spread_far_direction).all()
    assert (out.carry_direction == 1).sum() == 2
    assert (out.carry_direction == -1).sum() == 2


def test_future_prices_returns_and_revisions_cannot_change_past_signals():
    r, c = monthly_frames()
    expected = calculate(r, c)
    r.loc[r["month"] > "2023-12", ["near_return", "far_return"]] = 100
    revision = r[r["month"] == "2023-12"].copy()
    revision["available_at"] = "2024-03-01T00:00:00+00:00"
    revision["near_return"] = -0.9
    curve_revision = c.copy()
    curve_revision["available_at"] = "2024-03-01T00:00:00+00:00"
    curve_revision["near_price"] = 999
    pd.testing.assert_frame_equal(expected, calculate(pd.concat([r, revision]), pd.concat([c, curve_revision])))


def test_missing_month_is_not_bridged_or_replaced_by_a_later_month():
    r, c = monthly_frames()
    r = r[~((r["product"] == "SOYBEANS") & (r["month"] == "2023-04"))]
    out = calculate(r, c)
    assert np.isnan(out.loc["SOYBEANS", "basis_momentum"])
    assert out.loc["SOYBEANS", "trend_direction"] == 0
    assert out.loc["SOYBEANS", "carry_direction"] != 0


def test_six_product_threshold_and_negative_price_are_explicit():
    r, c = monthly_frames()
    c.loc[:2, "near_price"] = -37.63
    out = calculate(r, c)
    assert (out.carry_direction == 0).all()
    assert (out.carry_direction_status == "cash_fewer_than_six").all()
    assert np.isnan(out.loc["WTI", "carry"])
    assert "nonpositive" in out.loc["WTI", "reason"]
    assert (out.bm_outright_direction != 0).sum() == 4


def test_far_return_gap_does_not_silence_a_valid_trend():
    r, c = monthly_frames()
    r.loc[(r["product"] == "WTI") & (r["month"] == "2023-04"), "far_return"] = np.nan
    out = calculate(r, c)
    assert out.loc["WTI", "trend_direction"] == 1
    assert np.isnan(out.loc["WTI", "basis_momentum"])


def test_tie_order_is_independent_of_input_order():
    r, c = monthly_frames()
    c["near_price"] = 100
    expected = calculate(r, c)
    pd.testing.assert_frame_equal(expected, calculate(r.sample(frac=1, random_state=1), c.sample(frac=1, random_state=2)))
    assert set(expected.index[expected.carry_direction == -1]) == {"COPPER", "CORN"}
    assert set(expected.index[expected.carry_direction == 1]) == {"WHEAT_SRW", "WTI"}


@pytest.mark.parametrize("fault", ["duplicate", "naive", "early_month", "reversed_maturity", "infinity", "incomplete_month_decision"])
def test_reject_ambiguous_or_impossible_boundary_inputs(fault):
    r, c = monthly_frames()
    as_of = "2024-01-03T14:00:00+00:00"
    if fault == "duplicate":
        r = pd.concat([r, r.iloc[:1]])
    elif fault == "naive":
        c["available_at"] = "2024-01-02"
    elif fault == "early_month":
        c["available_at"] = "2023-12-30T00:00:00+00:00"
    elif fault == "reversed_maturity":
        c["far_delivery"] = "2024-01-01"
    elif fault == "infinity":
        r.loc[0, "near_return"] = np.inf
    else:
        as_of = "2023-12-31T14:00:00+00:00"
    with pytest.raises(ValueError):
        monthly_candidates(r, c, "2023-12", as_of)
