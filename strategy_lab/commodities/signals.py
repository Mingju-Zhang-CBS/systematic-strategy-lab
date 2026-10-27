"""Monthly curve hypotheses, separated from trading and data certification.

Inputs are upstream, same-contract rolling returns and a certified eligible
curve snapshot. This module neither manufactures a continuous price series nor
certifies the caller's calendar, listing history, execution or data rights.
"""

import numpy as np
import pandas as pd

from .engine import PRODUCTS


def monthly_candidates(returns, curves, month, as_of):
    """Compute the five predeclared requests using visible monthly observations.

    Returns: product, month, near_return, far_return, available_at.
    Curves: product, month, near_price, far_price, near_delivery, far_delivery,
    available_at, eligible. Month labels denote completed calendar months;
    upstream returns must include *all* scheduled holding intervals, not bridge
    missing marks. NaN returns retain an incomplete month. Monthly returns must
    already exclude invalid nonpositive-denominator holding intervals.

    Revisions have distinct available_at stamps. A later revision cannot alter
    an earlier decision. Quantities here are directions, not funded positions.
    """
    required = ((returns, "product month near_return far_return available_at"),
                (curves, "product month near_price far_price near_delivery far_delivery available_at eligible"))
    for frame, cols in required:
        if not set(cols.split()) <= set(frame):
            raise ValueError("missing monthly return/curve fields")
        if not set(frame["product"]) <= set(PRODUCTS):
            raise ValueError("unsupported product")
        if not frame.available_at.astype(str).str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True).all():
            raise ValueError("available_at requires an explicit UTC offset")
    r, c = returns.copy(), curves.copy()
    for frame in (r, c):
        frame["month"] = pd.to_datetime(frame["month"], errors="raise").dt.to_period("M")
        frame["available_at"] = pd.to_datetime(frame.available_at, utc=True, errors="raise")
        if frame.duplicated(["product", "month", "available_at"]).any():
            raise ValueError("ambiguous monthly version")
    for frame, cols in ((r, ["near_return", "far_return"]), (c, ["near_price", "far_price"])):
        for col in cols:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
            if np.isinf(frame[col]).any():
                raise ValueError("infinite economic input")
    for col in ("near_delivery", "far_delivery"):
        c[col] = pd.to_datetime(c[col], errors="raise")
    if not c.eligible.isin([True, False]).all():
        raise ValueError("eligible must be an explicit boolean")
    if ((c.far_delivery <= c.near_delivery) | c.near_delivery.isna() | c.far_delivery.isna()).any():
        raise ValueError("curve requires ordered distinct maturities")
    cutoff = pd.Timestamp(as_of)
    target_month = pd.Period(month, freq="M")
    if cutoff.tzinfo is None or cutoff.tz_convert("UTC").tz_localize(None) <= target_month.end_time:
        raise ValueError("as_of must carry an offset and follow the completed month")
    for frame in (r, c):
        if (frame.available_at.dt.tz_localize(None) <= frame["month"].dt.end_time).any():
            raise ValueError("a completed month cannot be available before month end")
    r = r[(r.available_at <= cutoff) & (r["month"] <= target_month)]
    c = c[(c.available_at <= cutoff) & (c["month"] == target_month)]
    r = r.sort_values("available_at").drop_duplicates(["product", "month"], keep="last")
    c = c.sort_values("available_at").drop_duplicates("product", keep="last").set_index("product")
    window = pd.period_range(target_month-11, target_month, freq="M")
    rows = []
    for product in PRODUCTS:
        row = dict(product=product, month=str(target_month), as_of=cutoff.isoformat(),
                   curve_eligible=False, carry=np.nan, trend=np.nan, basis_momentum=np.nan,
                   near_12m=np.nan, far_12m=np.nan, reason="missing_visible_eligible_curve")
        if product in c.index and c.loc[product, "eligible"]:
            curve = c.loc[product]
            row["curve_eligible"] = True
            reasons = []
            if np.isfinite(curve.near_price) and np.isfinite(curve.far_price) and min(curve.near_price, curve.far_price) > 0:
                days = (curve.far_delivery-curve.near_delivery).days
                row["carry"] = np.log(curve.near_price/curve.far_price)*365/days
            else:
                reasons.append("carry_nonpositive_or_missing_price")
            h = r[r["product"] == product].set_index("month").reindex(window)
            for field, output in (("near_return", "near_12m"), ("far_return", "far_12m")):
                values = h[field].to_numpy()
                if np.isfinite(values).all() and (values > -1).all():
                    row[output] = float(np.prod(1+values)-1)
                else:
                    reasons.append("incomplete_or_invalid_"+field+"_12m")
            row["trend"] = np.sign(row["near_12m"])
            row["basis_momentum"] = row["near_12m"]-row["far_12m"]
            row["reason"] = ";".join(reasons) if reasons else "eligible"
        rows.append(row)
    result = pd.DataFrame(rows).set_index("product")
    result["long_only_direction"] = result.curve_eligible.astype(int)
    result["trend_direction"] = result.trend.fillna(0).astype(int)
    result["bm_spread_near_direction"] = np.sign(result.basis_momentum).fillna(0).astype(int)
    result["bm_spread_far_direction"] = -result.bm_spread_near_direction
    for score, name in (("carry", "carry_direction"), ("basis_momentum", "bm_outright_direction")):
        result[name] = 0
        ranked = result[result[score].notna()].reset_index().sort_values([score, "product"], kind="stable")
        count = len(ranked)
        result[name+"_eligible_products"] = count
        result[name+"_status"] = "eligible" if count >= 6 else "cash_fewer_than_six"
        if count >= 6:
            result.loc[ranked["product"].iloc[:2], name] = -1
            result.loc[ranked["product"].iloc[-2:], name] = 1
    return result.reset_index()
