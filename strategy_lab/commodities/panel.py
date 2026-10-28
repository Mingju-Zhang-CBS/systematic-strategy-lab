"""Compile a current-vintage snapshot once for exploratory curve experiments."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import PRODUCTS
from .scheduled import scheduled_sessions
from .signals import _monthly_directions


@dataclass
class Panel:
    dates: pd.DatetimeIndex
    contracts: pd.DataFrame
    prices: np.ndarray
    volume: np.ndarray
    oi: np.ndarray
    deltas: np.ndarray
    pairs: np.ndarray
    deadlines: np.ndarray
    selection: pd.DataFrame
    monthly_returns: pd.DataFrame
    curves: pd.DataFrame
    signals: pd.DataFrame
    updates: dict
    closures: pd.DataFrame
    off_calendar: pd.DataFrame
    manifest: dict
    risk_cache: dict


def prepare(quotes, contracts, manifest, exit_buffer=5):
    """Validate once, then compile calendar, lagged pairs and monthly histories.

    Quote fields: contract/session/settlement/volume/open_interest.
    Contract fields: contract/product/delivery/first_notice/last_trade/valid_from/
    valid_to/listed_from/multiplier/usd_scale/outright_tick/unit_evidence.
    A single observed vendor specification interval is accepted per contract;
    this snapshot interface does not fabricate release-vintage knowledge.
    """
    for frame, fields in ((quotes, "contract session settlement volume open_interest"),
                          (contracts, "contract product delivery first_notice last_trade valid_from valid_to listed_from multiplier usd_scale outright_tick unit_evidence")):
        if not set(fields.split()) <= set(frame):
            raise ValueError("missing snapshot input columns")
    if (manifest.get("calendar_basis") != "authorized scheduled-settlement proxy"
            or manifest.get("data_kind") not in {"synthetic", "restricted", "public"}
            or not {"rights", "vintage", "source"} <= set(manifest)):
        raise ValueError("explicit calendar assumption, source, vintage and rights required")
    if exit_buffer < 1 or exit_buffer != int(exit_buffer):
        raise ValueError("positive integer exit buffer required")
    q, c = quotes.copy(), contracts.copy()
    q["session"] = pd.to_datetime(q.session, errors="raise").dt.normalize()
    for name in ("delivery", "first_notice", "last_trade", "valid_from", "valid_to", "listed_from"):
        c[name] = pd.to_datetime(c[name], errors="raise").dt.normalize()
    for frame, names in ((q, ["settlement", "volume", "open_interest"]), (c, ["multiplier", "usd_scale", "outright_tick"])):
        for name in names:
            frame[name] = pd.to_numeric(frame[name], errors="raise")
            if np.isinf(frame[name]).any():
                raise ValueError("infinite snapshot input")
    if (q.duplicated(["contract", "session"]).any() or c.contract.duplicated().any()
            or c.duplicated(["product", "delivery"]).any()):
        raise ValueError("ambiguous quote, specification or economic maturity")
    if (not set(c["product"]) <= set(PRODUCTS) or not set(q.contract) <= set(c.contract)
            or not c.unit_evidence.isin([True, False]).all()
            or (q[["volume", "open_interest"]] < 0).any().any()
            or c[["contract", "product", "delivery", "valid_from", "valid_to", "listed_from"]].isna().any().any()
            or c[["multiplier", "usd_scale", "outright_tick"]].isna().any().any()
            or (c[["multiplier", "usd_scale", "outright_tick"]] <= 0).any().any()
            or ((c.valid_to < c.valid_from) & c.unit_evidence).any()):
        raise ValueError("invalid identity, activity, units or specification interval")
    c = c.sort_values(["delivery", "contract"], kind="stable").reset_index(drop=True)
    start = q.session.min().to_period("M").start_time
    raw_end = q.session.max()
    end = max(q.session.max(), c.last_trade.max())+pd.Timedelta(days=40)
    dates, closures = scheduled_sessions(start, end)
    off_calendar = q[~q.session.isin(dates)].copy()
    q = q[q.session.isin(dates)]
    arrays = [q.pivot(index="session", columns="contract", values=field).reindex(index=dates, columns=c.contract).to_numpy(dtype=float)
              for field in ("settlement", "volume", "open_interest")]
    prices, volume, oi = arrays
    prices *= c.usd_scale.to_numpy()
    # A record outside its observed effective interval cannot support risk/marks.
    active = ((dates.to_numpy()[:, None] >= c.valid_from.to_numpy()[None, :])
              & (dates.to_numpy()[:, None] <= c.valid_to.to_numpy()[None, :]))
    active[:, ~c.unit_evidence.to_numpy()] = True  # keep visible blockers, never eligible risk inputs
    prices[~active] = np.nan
    del active
    deltas = np.full_like(prices, np.nan)
    deltas[1:] = np.diff(prices, axis=0)*c.multiplier.to_numpy()
    boundary = c[["first_notice", "last_trade"]].min(axis=1)
    deadlines = dates.searchsorted(boundary.fillna(dates[0]))-exit_buffer
    complete_boundary = c.first_notice.notna().to_numpy() & c.last_trade.notna().to_numpy()
    groups = [np.flatnonzero(c["product"].to_numpy() == product) for product in PRODUCTS]
    pairs = np.full((len(dates), len(PRODUCTS), 2), -1, dtype=np.int32)
    rows = []
    valid_from, valid_to = c.valid_from.to_numpy(), c.valid_to.to_numpy()
    listed, last_trade = c.listed_from.to_numpy(), c.last_trade.to_numpy()
    unit_evidence = c.unit_evidence.to_numpy()
    ids = c.contract.to_numpy()
    for day in range(2, len(dates)):
        obs = day-2
        day_date, obs_date = dates[day].to_datetime64(), dates[obs].to_datetime64()
        for j, product in enumerate(PRODUCTS):
            g = groups[j]
            interval = ((valid_from[g] <= obs_date) & (valid_to[g] >= day_date)) | ~unit_evidence[g]
            visible = ((listed[g] <= obs_date) & interval
                       & (pd.isna(last_trade[g]) | (last_trade[g] >= day_date))
                       & np.isfinite(prices[obs, g]) & (volume[obs, g] >= 100) & (oi[obs, g] >= 100))
            candidates = g[visible]
            # Unknown notice dates BLOCK the front; do not promote distant dates.
            candidates = candidates[(~complete_boundary[candidates]) | (deadlines[candidates] > day)]
            reason = "eligible"
            if len(candidates) < 2:
                reason = "fewer_than_two_lagged_liquid_contracts"
            elif not unit_evidence[candidates[:2]].all():
                reason = "front_specification_evidence_missing"
            elif not complete_boundary[candidates[:2]].all():
                reason = "front_notice_evidence_missing"
            else:
                pairs[day, j] = candidates[:2]
            selected = pairs[day, j]
            rows.append(dict(session=dates[day].date().isoformat(), observation=dates[obs].date().isoformat(),
                             product=product, near="" if selected[0] < 0 else ids[selected[0]],
                             far="" if selected[1] < 0 else ids[selected[1]], reason=reason,
                             first_position_history="not reconstructed"))
    # Unfunded unit reference histories: same held contract at both endpoints.
    # They define the signal, not executable filled strategy returns.
    references = np.full((len(dates), len(PRODUCTS), 2), np.nan)
    for day in range(3, len(dates)):
        for j in range(len(PRODUCTS)):
            for slot in range(2):
                key = pairs[day-1, j, slot]
                if key >= 0:
                    before, after = prices[day-1, key], prices[day, key]
                    if (before > 0 and after > 0 and np.isfinite(before+after)
                            and volume[day-1, key] > 0):
                        references[day, j, slot] = after/before-1
    monthly, curve_rows, observation_days = [], [], []
    periods = dates.to_period("M")
    for month in periods.unique():
        window = np.flatnonzero(periods == month)
        obs = window[-1]
        if obs+2 >= len(dates) or dates[obs] > raw_end:
            continue
        availability = (dates[obs+1]+pd.Timedelta(hours=23, minutes=59)).tz_localize("America/Chicago").tz_convert("UTC")
        observation_days.append((month, obs, obs+2, availability))
        for j, product in enumerate(PRODUCTS):
            values = references[window, j]
            compounded = [float(np.prod(1+values[:, slot])-1) if np.isfinite(values[:, slot]).all() else np.nan for slot in range(2)]
            monthly.append(dict(product=product, month=month, near_return=compounded[0], far_return=compounded[1],
                                available_at=availability, expected_intervals=len(window), near_valid_intervals=int(np.isfinite(values[:, 0]).sum()),
                                far_valid_intervals=int(np.isfinite(values[:, 1]).sum())))
            near, far = pairs[obs+2, j]
            eligible = near >= 0 and np.isfinite(prices[obs, [near, far]]).all()
            curve_rows.append(dict(product=product, month=month, observation=dates[obs],
                                   near_price=prices[obs, near] if eligible else np.nan,
                                   far_price=prices[obs, far] if eligible else np.nan,
                                   near_delivery=c.iloc[near].delivery if eligible else pd.Timestamp("2099-01-01"),
                                   far_delivery=c.iloc[far].delivery if eligible else pd.Timestamp("2099-02-01"),
                                   available_at=availability, eligible=eligible))
    monthly = pd.DataFrame(monthly)
    curves = pd.DataFrame(curve_rows)
    signals, updates = [], {}
    for month, obs, decision, availability in observation_days:
        cutoff = (dates[decision]+pd.Timedelta(hours=7)).tz_localize("America/Chicago").tz_convert("UTC")
        r = monthly[(monthly["month"] <= month) & (monthly.available_at <= cutoff)]
        curve = curves[curves["month"] == month].set_index("product")
        score = _monthly_directions(r, curve, month, cutoff)
        score["observation"] = dates[obs]
        score["decision_index"] = decision
        updates[decision] = score
        signals.append(score)
    return Panel(dates, c, prices, volume, oi, deltas, pairs, deadlines, pd.DataFrame(rows),
                 monthly, curves, pd.concat(signals, ignore_index=True), updates, closures,
                 off_calendar, dict(manifest), {})
