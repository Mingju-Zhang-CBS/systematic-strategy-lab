"""Invented monthly observations: signal directions, not account performance."""

import pandas as pd

from strategy_lab.commodities.engine import PRODUCTS
from strategy_lab.commodities.signals import monthly_candidates

returns, curves = [], []
for i, product in enumerate(PRODUCTS):
    for month in pd.period_range("2023-01", "2023-12", freq="M"):
        returns.append(dict(product=product, month=str(month), near_return=.001*(i-3),
                            far_return=.0005, available_at=((month+1).start_time.tz_localize("UTC")+pd.Timedelta(days=1)).isoformat()))
    curves.append(dict(product=product, month="2023-12", near_price=97.+i, far_price=100.,
                       near_delivery="2024-03-01", far_delivery="2024-06-01", eligible=True,
                       available_at="2024-01-02T00:00:00+00:00"))
table = monthly_candidates(pd.DataFrame(returns), pd.DataFrame(curves), "2023-12", "2024-01-03T14:00:00+00:00")
print("SYNTHETIC INPUTS | independent curve hypotheses | no capital, fills or strategy returns")
print(table[["product", "carry", "near_12m", "basis_momentum", "trend_direction", "carry_direction", "bm_outright_direction", "bm_spread_near_direction"]].round(6).to_string(index=False))
print("Carry > 0 means a downward-sloping price curve. It does not guarantee a realized return.")
print("Basis-momentum compares compounded near/far rolling-return histories, not today's price spread.")
