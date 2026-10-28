"""Invented curves and contract terms for the funded-research test boundary."""

import numpy as np
import pandas as pd

from .engine import PRODUCTS
from .fixture import SPECS
from .scheduled import scheduled_sessions


def research_frames(seed=20261026):
    rng = np.random.default_rng(seed)
    dates, _ = scheduled_sessions("2019-01-01", "2022-12-31")
    quotes, contracts = [], []
    for j, product in enumerate(PRODUCTS):
        size, scale, tick, level = SPECS[product]
        common = np.cumsum(rng.normal(0, .003, len(dates)))
        for m, delivery in enumerate(pd.to_datetime(["2021-06-01", "2021-12-01", "2022-06-01", "2022-12-01"])):
            key = f"SYN_RESEARCH_{product}_{m}"
            contracts.append(dict(contract=key, product=product, delivery=delivery,
                                  first_notice=delivery-pd.Timedelta(days=10), last_trade=delivery-pd.Timedelta(days=5),
                                  valid_from="2018-01-01", valid_to="2025-12-31", listed_from="2018-01-01",
                                  multiplier=size, usd_scale=scale, outright_tick=tick, unit_evidence=True))
            values = level*np.exp(common+.025*m+np.cumsum(rng.normal(.00002*(j-3), .0003, len(dates))))
            for day, value in zip(dates, values):
                quotes.append(dict(contract=key, session=day, settlement=value, volume=50000, open_interest=10000))
    manifest = dict(data_kind="synthetic", rights="Original generated examples; no vendor records",
                    vintage="invented; seed="+str(seed), source="research_fixture",
                    calendar_basis="authorized scheduled-settlement proxy")
    return pd.DataFrame(quotes), pd.DataFrame(contracts), manifest
