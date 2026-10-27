"""Original synthetic eight-product fixtures. No vendor observations are embedded."""

import numpy as np
import pandas as pd

from .engine import PRODUCTS, Protocol, validate


SPECS = {
    "WTI": (1000, 1, .01, 70),
    "NATURAL_GAS": (10000, 1, .001, 3),
    "GOLD": (100, 1, .10, 2000),
    "SILVER": (5000, 1, .005, 25),
    "COPPER": (25000, 1, .0005, 4),
    "CORN": (5000, .01, .0025, 450),
    "WHEAT_SRW": (5000, .01, .0025, 600),
    "SOYBEANS": (5000, .01, .0025, 1200),
}


def frames(seed=20261026):
    """Invented prices, identities, maturities and calendars, including a closure.

    Realistic public unit conventions are used to test conversion. Synthetic
    session/expiry dates explicitly are NOT historical exchange facts.
    """
    rng = np.random.default_rng(seed)
    base = pd.bdate_range("2024-01-02", periods=350)
    calendars, contracts, quotes = [], [], []
    known = "2023-12-01T00:00:00+00:00"
    for j, product in enumerate(PRODUCTS):
        dates = base.delete(142 + j)  # distinct, deliberately synthetic closures
        size, scale, tick, level = SPECS[product]
        daily = rng.normal(0, level * .002, len(dates)).cumsum()
        for i, date in enumerate(dates):
            calendars.append(dict(product=product, session=date.date().isoformat(),
                                  decision_at=f"{date.date()}T14:00:00+00:00",
                                  settlement_at=f"{date.date()}T{19 if j > 4 else 20}:00:00+00:00",
                                  known_at=known, verified=True, source="original synthetic calendar"))
        for m, boundary_index in enumerate((168, 202, 245, 290)):
            contract = f"SYN_{product}_{m+1}"
            # The synthetic risk boundary can be earlier than first notice.
            boundary = dates[boundary_index]
            contracts.append(dict(contract=contract, product=product, delivery=dates[boundary_index+8].date().isoformat(),
                                  listed_at=known, known_at=known, valid_from="2023-12-01", valid_to="2026-12-31",
                                  first_notice=dates[boundary_index+1].date().isoformat(),
                                  first_position=boundary.date().isoformat(),
                                  last_trade=dates[boundary_index+4].date().isoformat(), multiplier=size,
                                  usd_scale=scale, outright_tick=tick, boundary_verified=True,
                                  listing_verified=True, spec_verified=True, source="original synthetic contract"))
            prices = level + daily + m * level * .015 + rng.normal(0, level * .0003, len(dates))
            for i, date in enumerate(dates[:-1]):
                quotes.append(dict(contract=contract, session=date.date().isoformat(),
                                   settlement=round(prices[i] * scale / (tick/5)) * (tick/5) / scale,
                                   volume=10000 + 50*j + m*100, open_interest=20000,
                                   available_at=f"{dates[i+1].date()}T22:00:00+00:00"))
    manifest = dict(data_kind="synthetic", rights="Original generated fixture, MIT code; no licensed market prices",
                    source="strategy_lab.commodities.fixture; seed="+str(seed),
                    calendar_basis="Invented per-product sessions, not an exchange holiday archive")
    return pd.DataFrame(quotes), pd.DataFrame(contracts), pd.DataFrame(calendars), manifest, base[132], base[216]


def fixture(protocol=Protocol()):
    return validate(*frames(), protocol)
