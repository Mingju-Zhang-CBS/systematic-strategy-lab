"""A daily, explicitly constrained futures ledger, not an execution replay.

The only public boundary is validate(). run() consumes its normalized Inputs.
Missing economic observations become logged outcomes, not invented prices.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


PRODUCTS = ("WTI", "NATURAL_GAS", "GOLD", "SILVER", "COPPER", "CORN", "WHEAT_SRW", "SOYBEANS")


@dataclass(frozen=True)
class Protocol:
    capital: float = 1_000_000
    exit_buffer: int = 5
    commission: float = 2.50
    slippage_ticks: float = 1
    participation: float = 0.01
    minimum_oi: int = 100
    reserve_rate: float = 0.10
    reserve_limit: float = 0.50
    gross_limit: float = 3.0
    annual_risk_cap: float = 0.10
    risk_min_days: int = 126
    risk_window: int = 252
    price_window: int = 60
    units: int = 1


@dataclass
class Inputs:
    quotes: pd.DataFrame
    contracts: pd.DataFrame
    calendar: pd.DataFrame
    manifest: dict
    start: pd.Timestamp
    end: pd.Timestamp


def validate(quotes, contracts, calendar, manifest, start, end, protocol=Protocol()):
    """Validate and normalize once; return data eligible for internal functions.

    Unverified *economic evidence* is retained and later quarantined. Invalid
    structure, impossible clocks or ambiguous keys fail here with a clear error.
    All timestamps in input CSVs must carry a UTC offset.
    """
    required = {
        "quotes": (quotes, "contract session settlement volume open_interest available_at"),
        "contracts": (contracts, "contract product delivery listed_at known_at valid_from valid_to first_notice last_trade first_position multiplier usd_scale outright_tick boundary_verified listing_verified spec_verified source"),
        "calendar": (calendar, "product session decision_at settlement_at known_at verified source"),
    }
    for name, (frame, columns) in required.items():
        missing = set(columns.split()) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing columns {sorted(missing)}")
    if not {"data_kind", "rights", "source", "calendar_basis"} <= manifest.keys():
        raise ValueError("manifest: data_kind, rights, source and calendar_basis are required")
    if manifest["data_kind"] not in {"synthetic", "restricted", "public"}:
        raise ValueError("manifest: invalid data_kind")
    p = asdict(protocol)
    if not all(np.isfinite(x) and x >= 0 for x in p.values()):
        raise ValueError("protocol: values must be finite and nonnegative")
    if (protocol.capital <= 0 or protocol.units < 1 or protocol.units != int(protocol.units)
            or protocol.exit_buffer < 1 or protocol.exit_buffer != int(protocol.exit_buffer)
            or not 0 < protocol.participation <= 1 or not 0 < protocol.reserve_limit <= 1
            or protocol.reserve_rate <= 0 or protocol.gross_limit <= 0
            or not 2 <= protocol.risk_min_days <= protocol.risk_window
            or protocol.risk_window != int(protocol.risk_window)
            or protocol.risk_min_days != int(protocol.risk_min_days)
            or protocol.price_window < 1 or protocol.price_window != int(protocol.price_window)):
        raise ValueError("protocol: invalid integer windows, capital, participation or risk limits")
    q, c, k = (frame.copy() for frame in (quotes, contracts, calendar))
    for frame, names in ((q, ["session"]), (c, ["delivery", "valid_from", "valid_to", "first_notice", "last_trade", "first_position"]), (k, ["session"])):
        for col in names:
            frame[col] = pd.to_datetime(frame[col], errors="raise").dt.normalize()
    for frame, names in ((q, ["available_at"]), (c, ["listed_at", "known_at"]), (k, ["decision_at", "settlement_at", "known_at"])):
        for col in names:
            # Reject naive strings: converting them to UTC would silently invent a timezone.
            if not frame[col].astype(str).str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True).all():
                raise ValueError(f"{col}: timestamps must have explicit timezone offsets")
            frame[col] = pd.to_datetime(frame[col], utc=True, errors="raise")
    for frame, cols in ((q, ["settlement", "volume", "open_interest"]), (c, ["multiplier", "usd_scale", "outright_tick"])):
        for col in cols:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
            if np.isinf(frame[col]).any():
                raise ValueError(f"{col}: infinity is invalid")
    if (c[["multiplier", "usd_scale", "outright_tick"]].isna().any().any()
            or (c[["multiplier", "usd_scale", "outright_tick"]] <= 0).any().any()
            or (q[["volume", "open_interest"]] < 0).any().any()):
        raise ValueError("invalid units or negative activity")
    for frame, cols in ((c, ["boundary_verified", "listing_verified", "spec_verified"]), (k, ["verified"])):
        for col in cols:
            if not frame[col].isin([True, False]).all():
                raise ValueError(f"{col}: explicit boolean required")
    if (q.duplicated(["contract", "session", "available_at"]).any()
            or c.duplicated(["contract", "valid_from", "known_at"]).any()
            or k.duplicated(["product", "session"]).any()):
        raise ValueError("ambiguous duplicate quote, metadata version or calendar session")
    if c[["contract", "product", "delivery", "valid_from", "valid_to"]].isna().any().any():
        raise ValueError("contract identity and effective interval are required")
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("start must not follow end")
    if not set(c["product"]) <= set(PRODUCTS) or not set(k["product"]) <= set(PRODUCTS):
        raise ValueError("unsupported product")
    if (c.groupby("contract")["product"].nunique() > 1).any():
        raise ValueError("a contract cannot change economic product")
    if not set(q["contract"]) <= set(c["contract"]):
        raise ValueError("quote without contract identity")
    if (c["valid_to"] < c["valid_from"]).any():
        raise ValueError("reversed specification interval")
    identity = c.drop_duplicates("contract").set_index("contract")["product"]
    q["product"] = q["contract"].map(identity)
    clocks = q.merge(k, on=["product", "session"], how="left", validate="many_to_one")
    if clocks["settlement_at"].isna().any() or (clocks["available_at"] < clocks["settlement_at"]).any():
        raise ValueError("quotes must map to a supplied session and cannot predate its settlement clock")
    if ((k["decision_at"] >= k["settlement_at"]).any()
            or (k["decision_at"].dt.tz_localize(None).dt.normalize() != k["session"]).any()
            or (k.groupby("session")["decision_at"].nunique() > 1).any()):
        raise ValueError("use one shared pre-settlement UTC decision per date; local settlement clocks may differ")
    # Current-vintage revisions can be seen by a later decision, never by an earlier one.
    # The latest revision defines the retrospective end-of-day accounting reference.
    return Inputs(q.sort_values(["contract", "session", "available_at"]),
                  c.sort_values(["contract", "valid_from", "known_at"]),
                  k.sort_values(["product", "session"]), dict(manifest),
                  pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize())


def run(data: Inputs, protocol=Protocol()):
    """Run a fixed-size near/far *accounting diagnostic*, not a carry strategy.

    Targets are +units N1 / -units N2, with portfolio-wide scaling DOWN only.
    Risk, liquidity and selection see available observations only. Settlement
    references are used afterward to mark old positions and evaluate fills.
    """
    q, c, k = data.quotes, data.contracts, data.calendar
    retrospective = q.drop_duplicates(["contract", "session"], keep="last").set_index(["contract", "session"])
    positions, held_specs, marks = {}, {}, {}
    cash = protocol.capital
    ledger, trades, decisions, selections, events, holdings = [], [], [], [], [], []
    status = "completed_accounting_diagnostic"
    calendars = {product: frame.set_index("session") for product, frame in k.groupby("product")}

    def event(day, product, code, detail):
        events.append(dict(session=str(day.date()), product=product, code=code, detail=detail))

    for day in sorted(k.loc[k["session"].between(data.start, data.end), "session"].unique()):
        day = pd.Timestamp(day)
        sessions = k[k["session"] == day].sort_values(["settlement_at", "product"])
        decision_at = sessions.iloc[0]["decision_at"]
        # No same-session observation, even if an erroneous early vendor stamp exists.
        visible = q[(q["available_at"] <= decision_at) & (q["session"] < day)]
        visible = visible.drop_duplicates(["contract", "session"], keep="last")
        history = {key: frame.sort_values("session") for key, frame in visible.groupby("contract")}
        known = c[(c["known_at"] <= decision_at) & (c["valid_from"] <= day) & (c["valid_to"] >= day)]
        known = known.sort_values(["valid_from", "known_at"]).drop_duplicates("contract", keep="last")
        spec = known.set_index("contract").to_dict("index")
        targets = dict(positions)
        group_targets = {}
        exits = {}
        for session in sessions.itertuples(index=False):
            product = session.product
            calendar = calendars[product]
            current = {key: value for key, value in positions.items() if held_specs[key]["product"] == product}
            candidates = []
            for row in known[known["product"] == product].itertuples(index=False):
                reason = "eligible"
                deadline = pd.NaT
                boundary = min((x for x in (row.first_notice, row.last_trade, row.first_position) if pd.notna(x)), default=pd.NaT)
                if not (row.boundary_verified and row.spec_verified and row.listing_verified) or pd.isna(row.first_notice) or pd.isna(row.last_trade):
                    reason = "unverified_contract_evidence"
                elif not session.verified or session.known_at > decision_at:
                    reason = "unverified_calendar"
                elif row.listed_at > decision_at:
                    reason = "not_yet_listed"
                else:
                    before = calendar[calendar.index < boundary]
                    if len(before) < protocol.exit_buffer or calendar.index.max() < boundary:
                        reason = "calendar_does_not_cover_boundary"
                    else:
                        buffer = before.tail(protocol.exit_buffer)
                        if not buffer["verified"].all() or (buffer["known_at"] > decision_at).any():
                            reason = "unverified_deadline_calendar"
                        else:
                            deadline = buffer.index[0]
                            exits[row.contract] = deadline
                            if day >= deadline:
                                reason = "inside_delivery_buffer"
                h = history.get(row.contract)
                if reason == "eligible":
                    if h is None or h.iloc[-1]["session"] != calendar.index[max(0, calendar.index.get_loc(day) - 2)]:
                        reason = "missing_required_lagged_observation"
                    elif (pd.isna(h.iloc[-1]["settlement"]) or pd.isna(h.iloc[-1]["volume"])
                          or pd.isna(h.iloc[-1]["open_interest"]) or h.iloc[-1]["volume"] <= 0
                          or h.iloc[-1]["open_interest"] < protocol.minimum_oi):
                        reason = "lagged_activity_or_price_failure"
                selections.append(dict(session=str(day.date()), product=product, contract=row.contract,
                                       delivery=str(row.delivery.date()), reason=reason,
                                       safe_exit="" if pd.isna(deadline) else str(deadline.date())))
                if reason == "eligible":
                    candidates.append(row)
            candidates.sort(key=lambda row: (row.delivery, row.contract))
            # Duplicate economic maturity is an identity error, never a second leg.
            if len({r.delivery for r in candidates}) != len(candidates):
                event(day, product, "ambiguous_maturity", "No new pair; existing position scheduled for exit")
                candidates = []
            pair = {r.contract: protocol.units * sign for r, sign in zip(candidates[:2], (1, -1))} if len(candidates) >= 2 else {}
            if not pair:
                event(day, product, "no_qualified_pair", "No eligible near/far pair; target flat")
            for key in current:
                targets.pop(key)
                # A held contract may not disappear because a metadata version expires.
                if key not in exits:
                    event(day, product, "held_contract_evidence_lost", key)
                    status = "failed_held_contract_evidence"
                elif any(spec[key][field] != held_specs[key][field]
                         for field in ("multiplier", "usd_scale", "outright_tick")):
                    event(day, product, "held_contract_unit_change", key)
                    status = "failed_held_contract_evidence"
            targets.update(pair)
            group_targets[product] = (current, pair)
        if status.startswith("failed"):
            break

        # Fixed-size stage-2 request. Estimate portfolio dollar risk on common dates,
        # using adjacent local sessions only; missing days are NOT zero returns.
        price_basis, risk_series = {}, {}
        unit_history_ok = True
        for key in targets:
            h = history[key]
            s = spec.get(key, held_specs.get(key))
            h = h[h["session"].between(s["valid_from"], s["valid_to"])]
            values = h.set_index("session")["settlement"].reindex(calendars[s["product"]].index)
            delta = values.diff().dropna() * s["usd_scale"] * s["multiplier"]
            risk_series[key] = delta
            if len(delta.tail(protocol.price_window)) < min(40, protocol.price_window):
                event(day, s["product"], "insufficient_unit_risk_history", key)
                unit_history_ok = False
            recent = h["settlement"].dropna().tail(protocol.price_window).abs() * s["usd_scale"]
            price_basis[key] = (max(float(recent.iloc[-1]), float(recent.median())) * s["multiplier"]
                                if not recent.empty else 0.0)
        factor, risk_before = (1.0 if unit_history_ok else 0.0), 0.0
        if targets:
            matrix = pd.concat(risk_series, axis=1).dropna().tail(protocol.risk_window)
            if len(matrix) < protocol.risk_min_days:
                factor = 0.0
                event(day, "PORTFOLIO", "insufficient_risk_history", f"{len(matrix)} common days; need {protocol.risk_min_days}")
            else:
                weights = np.array([targets[key] for key in matrix.columns])
                risk_before = float(np.sqrt(max(0, weights @ matrix.cov().to_numpy() @ weights) * 252))
                if risk_before > 0:
                    factor = min(factor, protocol.annual_risk_cap * cash / risk_before)
            gross = sum(abs(n) * price_basis[key] for key, n in targets.items())
            # Commission/slippage reserve keeps initial modeled constraints after fees.
            projected_fees = sum(abs(targets.get(key, 0) - positions.get(key, 0)) *
                                 (protocol.commission + protocol.slippage_ticks * spec.get(key, held_specs.get(key))["outright_tick"] *
                                  spec.get(key, held_specs.get(key))["multiplier"])
                                 for key in sorted(set(targets) | set(positions)))
            budget_cash = max(0, cash - projected_fees)
            if gross > 0:
                factor = min(factor, protocol.gross_limit * budget_cash / gross,
                             protocol.reserve_limit * budget_cash / (protocol.reserve_rate * gross))
        # Pair quantities round together toward zero. Closed products cannot be traded.
        for product, (current, pair) in group_targets.items():
            scaled = {key: int(np.trunc(n * factor)) for key, n in pair.items()}
            scaled = {key: n for key, n in scaled.items() if n}
            group_targets[product] = (current, scaled)
            if pair and not scaled:
                event(day, product, "integer_risk_or_funding_rejection", f"Scale {factor:.8f} leaves no paired integer contracts")
        for product, (current, pair) in group_targets.items():
            for key in sorted(set(current) | set(pair)):
                h = history.get(key)
                latest = h.iloc[-1] if h is not None else None
                decisions.append(dict(session=str(day.date()), decision_at=decision_at.isoformat(), product=product,
                                      contract=key, old=current.get(key, 0), target=pair.get(key, 0),
                                      observation="" if latest is None else str(latest["session"].date()),
                                      available_at="" if latest is None else latest["available_at"].isoformat(),
                                      risk_scale=factor, risk_before_usd=risk_before))

        opening_cash, vm, fees, stale = cash, 0.0, 0.0, []
        for session in sessions.itertuples(index=False):
            product = session.product
            current, pair = group_targets[product]
            # Mark OLD holdings first: different delivery prices on roll are not P&L.
            for key, n in current.items():
                quote_key = (key, day)
                if quote_key not in retrospective.index or pd.isna(retrospective.loc[quote_key, "settlement"]):
                    stale.append(key)
                    event(day, product, "stale_mark", key)
                else:
                    price = float(retrospective.loc[quote_key, "settlement"]) * held_specs[key]["usd_scale"]
                    change = n * held_specs[key]["multiplier"] * (price - marks[key])
                    vm += change
                    cash += change
                    marks[key] = price
            if cash <= 0:
                status = "failed_nonpositive_equity"
                event(day, product, status, "Funding path stopped; no external capital and no percentage-return continuation")
                break
            changes = {key: pair.get(key, 0) - current.get(key, 0) for key in sorted(set(current) | set(pair))}
            changes = {key: n for key, n in changes.items() if n}
            if changes:
                failure = ""
                if not session.verified or session.known_at > decision_at:
                    failure = "unverified_execution_calendar"
                for key, n in sorted(changes.items()):
                    h = history.get(key)
                    if h is None:
                        failure = "missing_lagged_exit_activity"
                    elif (pd.isna(h.iloc[-1]["volume"]) or abs(n) > np.floor(protocol.participation * h.iloc[-1]["volume"])):
                        failure = "lagged_participation_limit"
                    quote_key = (key, day)
                    if quote_key not in retrospective.index or pd.isna(retrospective.loc[quote_key, "settlement"]):
                        failure = "missing_execution_reference"
                    elif pd.isna(retrospective.loc[quote_key, "volume"]) or retrospective.loc[quote_key, "volume"] <= 0:
                        failure = "zero_or_missing_execution_activity"
                if failure:
                    event(day, product, "unfilled_basket", failure)
                else:
                    candidate_positions = dict(positions)
                    candidate_specs = dict(held_specs)
                    candidate_marks = dict(marks)
                    cost = 0.0
                    for key, delta in changes.items():
                        s = spec.get(key, held_specs.get(key))
                        candidate_specs[key] = s
                        candidate_marks[key] = float(retrospective.loc[(key, day), "settlement"]) * s["usd_scale"]
                        cost += abs(delta) * (protocol.commission + protocol.slippage_ticks * s["outright_tick"] * s["multiplier"])
                        candidate_positions[key] = pair.get(key, 0)
                    candidate_positions = {key: n for key, n in candidate_positions.items() if n}
                    gross_after = 0.0
                    for key, n in candidate_positions.items():
                        s = candidate_specs[key]
                        h = history.get(key)
                        median = (h["settlement"].dropna().tail(protocol.price_window).abs().median() * s["usd_scale"]
                                  if h is not None else abs(candidate_marks[key]))
                        gross_after += abs(n) * s["multiplier"] * max(abs(candidate_marks[key]), median)
                    after_fee = cash - cost
                    increasing = any(abs(pair.get(key, 0)) > abs(current.get(key, 0)) for key in changes)
                    bound = min(protocol.gross_limit, protocol.reserve_limit / protocol.reserve_rate) * after_fee
                    if after_fee <= 0 or (increasing and gross_after > bound):
                        event(day, product, "unfilled_basket", "post_mark_funding_limit; frozen request not resized using execution prices")
                    else:
                        for key, delta in sorted(changes.items()):
                            s = candidate_specs[key]
                            commission = abs(delta) * protocol.commission
                            slippage = abs(delta) * protocol.slippage_ticks * s["outright_tick"] * s["multiplier"]
                            trades.append(dict(session=str(day.date()), settlement_at=session.settlement_at.isoformat(),
                                               product=product, contract=key, delta=delta,
                                               settlement_reference=candidate_marks[key], multiplier=s["multiplier"],
                                               commission=commission, slippage=slippage, total_cost=commission + slippage,
                                               reason="entry" if not current else "roll_or_risk_rebalance"))
                        positions, held_specs, marks = candidate_positions, candidate_specs, candidate_marks
                        cash = after_fee
                        fees += cost
            # A failed exit remains held. Deadline failure stops the entire funded path.
            for key, n in positions.items():
                if held_specs[key]["product"] == product and day >= exits[key]:
                    status = "failed_safe_exit"
                    event(day, product, status, f"{key}: {n} contracts remain held at safe-exit deadline")
            if status.startswith("failed"):
                break
        gross = 0.0
        for key, n in positions.items():
            s = held_specs[key]
            h = history.get(key)
            median = h["settlement"].dropna().tail(protocol.price_window).abs().median() * s["usd_scale"] if h is not None else abs(marks[key])
            exposure = abs(n) * s["multiplier"] * max(abs(marks[key]), median)
            gross += exposure
            holdings.append(dict(session=str(day.date()), product=s["product"], contract=key,
                                 quantity=n, mark=marks[key], gross_proxy=exposure, stale=key in stale))
        reserve = protocol.reserve_rate * gross
        if cash > 0 and (gross > protocol.gross_limit * cash or reserve > protocol.reserve_limit * cash):
            event(day, "PORTFOLIO", "constraint_breach", "Reduction requested at next feasible decision; no instantaneous free liquidation")
        ledger.append(dict(session=str(day.date()), opening_equity=opening_cash, variation_margin=vm,
                           costs=fees, equity=cash, gross_proxy=gross, reserve=reserve, free_cash=cash-reserve,
                           stale_contracts=len(stale), positions=len(positions), status=status))
        if status.startswith("failed"):
            break
    if not trades and not status.startswith("failed"):
        status = "completed_no_qualified_trades"
    return dict(status=status, ledger=pd.DataFrame(ledger, columns=["session", "opening_equity", "variation_margin", "costs", "equity", "gross_proxy", "reserve", "free_cash", "stale_contracts", "positions", "status"]),
                trades=pd.DataFrame(trades, columns=["session", "settlement_at", "product", "contract", "delta", "settlement_reference", "multiplier", "commission", "slippage", "total_cost", "reason"]),
                decisions=pd.DataFrame(decisions, columns=["session", "decision_at", "product", "contract", "old", "target", "observation", "available_at", "risk_scale", "risk_before_usd"]),
                selections=pd.DataFrame(selections, columns=["session", "product", "contract", "delivery", "reason", "safe_exit"]),
                events=pd.DataFrame(events, columns=["session", "product", "code", "detail"]),
                holdings=pd.DataFrame(holdings, columns=["session", "product", "contract", "quantity", "mark", "gross_proxy", "stale"]),
                protocol=asdict(protocol), manifest=data.manifest)
