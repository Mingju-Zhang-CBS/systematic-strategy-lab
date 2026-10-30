"""Funded exploratory futures experiments on a compiled snapshot panel.

Daily EOD references, assumed two-session availability and proxy reserves do not
reconstruct intraday fills, historical SPAN or complete point-in-time vintages.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .engine import PRODUCTS


STRATEGIES = {
    "long_only": "long_only_direction", "trend": "trend_direction",
    "carry": "carry_direction", "bm_outright": "bm_outright_direction",
    "bm_spread": "bm_spread_near_direction",
}
SECTORS = {"WTI":"energy", "NATURAL_GAS":"energy", "GOLD":"metals", "SILVER":"metals",
           "COPPER":"metals", "CORN":"agriculture", "WHEAT_SRW":"agriculture", "SOYBEANS":"agriculture"}


def _entry_budget(units, capacity, remaining, lead, spare):
    """Shared normalized-unit rule for engine, tests and fixed-state replay.

    Snapshot/protocol validation belongs to the account boundary. Entry books at
    EOD, so remaining excludes entry day and includes the old hard deadline.
    """
    drain = (units+capacity-1)//capacity if capacity > 0 else None
    lead_ok = remaining > lead
    drain_ok = drain is not None and remaining > drain+spare
    reasons = []
    if capacity == 0:
        reasons.append("no_exit_capacity")
    if not lead_ok:
        reasons.append("inside_retirement_lead")
    if not drain_ok:
        reasons.append("insufficient_drain_budget")
    return dict(target_units=units, conservative_capacity=capacity, remaining_exit_sessions=remaining,
                required_drain_sessions=drain, lead_ok=lead_ok, drain_ok=drain_ok,
                admitted=not reasons, reason="admitted" if not reasons else ";".join(reasons))


@dataclass(frozen=True)
class ResearchProtocol:
    start: str = "2005-01-01"
    end: str = "2025-12-31"
    capital: float = 1_000_000
    commission: float = 2.5
    slippage_ticks: float = 1
    participation: float = .01
    reserve_rate: float = .10
    reserve_limit: float = .50
    gross_limit: float = 3
    annual_risk_cap: float = .10
    unit_window: int = 60
    unit_minimum: int = 40
    covariance_window: int = 252
    covariance_minimum: int = 126
    extra_delay: int = 0
    exclude_sector: str = ""
    execution_policy: str = "coupled"
    exit_lead: int = 0
    capacity_window: int = 5
    drain_buffer: int = 2
    entry_budget: bool = False


def run_research(tape, strategy, protocol=ResearchProtocol(), detail=True, stress=None):
    """Consume the once-validated panel and a predeclared protocol.

    Equal standalone unit-risk budgets are set at month changes or pair changes;
    intermediate requests may only reduce size. Every request is frozen before
    the execution reference. The legacy coupled basket remains the default;
    exit_first separates all portfolio reductions from optional replacement risk.
    """
    p = protocol
    numbers = (p.capital, p.commission, p.slippage_ticks, p.participation, p.reserve_rate, p.reserve_limit,
               p.gross_limit, p.annual_risk_cap, p.unit_window, p.unit_minimum, p.covariance_window, p.covariance_minimum, p.extra_delay)
    if (not all(np.isfinite(v) and v >= 0 for v in numbers) or p.capital <= 0
            or not 0 < p.participation <= 1 or not 0 < p.reserve_limit <= 1 or p.reserve_rate <= 0
            or p.gross_limit <= 0 or not 2 <= p.unit_minimum <= p.unit_window
            or not 2 <= p.covariance_minimum <= p.covariance_window
            or any(v != int(v) for v in (p.unit_window, p.unit_minimum, p.covariance_window, p.covariance_minimum, p.extra_delay))
            or p.exclude_sector not in {"", "energy", "metals", "agriculture"}
            or p.execution_policy not in {"coupled", "exit_first", "staged"}
            or any(not np.isfinite(v) or v != int(v) or v < 0 for v in (p.exit_lead, p.capacity_window, p.drain_buffer))
            or p.capacity_window < 1 or (p.exit_lead > 0 and p.execution_policy != "staged")
            or not isinstance(p.entry_budget, bool)
            or (p.entry_budget and (p.execution_policy != "staged" or p.exit_lead <= 0))
            or (stress is not None and (p.execution_policy != "staged" or not p.entry_budget)) or strategy not in STRATEGIES):
        raise ValueError("invalid research protocol or strategy")
    dates, c, prices = tape.dates, tape.contracts, tape.prices
    keys = c.contract.to_numpy()
    contract_products = c["product"].to_numpy()
    multipliers, ticks = c.multiplier.to_numpy(), c.outright_tick.to_numpy()
    product_indices = [np.flatnonzero(c["product"].to_numpy() == product) for product in PRODUCTS]
    is_spread = strategy == "bm_spread"
    column = STRATEGIES[strategy]
    active_days = np.flatnonzero((dates >= pd.Timestamp(p.start)) & (dates <= pd.Timestamp(p.end)))
    if (not len(active_days) or active_days[0] < 2 or pd.Timestamp(p.end) > dates[-1]
            or pd.Timestamp(p.start) < dates[0]):
        raise ValueError("research scope needs two preceding scheduled sessions and a covered end date")
    positions = np.zeros(len(c), dtype=np.int64)
    marks = np.full(len(c), np.nan)
    cash = float(p.capital)
    ledger, trades, decisions, events, holdings, pnl = [], [], [], [], [], []
    old_signature = None
    last_requested = np.zeros(len(PRODUCTS))
    directions = np.zeros(len(PRODUCTS))
    score = None
    pending = np.zeros(len(PRODUCTS), dtype=bool)
    exit_goals = np.zeros(len(c), dtype=np.int64)
    retired_front = np.full(len(PRODUCTS), -1, dtype=np.int64)
    exit_plans = []
    admissions = []
    stress_budgets = []
    stress_sessions = []
    observed_capacity = None if stress is None else np.floor(np.floor(p.participation*tape.volume)*stress.capacity_factor)
    updates = {i+p.extra_delay:s for i, s in tape.updates.items()}
    earlier = [i for i in updates if i < active_days[0]]
    if earlier:
        score = updates[max(earlier)].set_index("product").reindex(PRODUCTS)
        directions = score[column].to_numpy(dtype=float)
    equity_history = {}
    status = "completed_exploratory_path"
    for day in active_days:
        obs = day-2
        reserve_rate = p.reserve_rate if stress is None else p.reserve_rate*stress.margin_factor[day]
        new_month = day in updates
        if new_month:
            score = updates[day].set_index("product").reindex(PRODUCTS)
            directions = score[column].to_numpy(dtype=float)
        allowed = np.array([SECTORS[name] != p.exclude_sector for name in PRODUCTS])
        # Sector exclusions do not rerank the remaining names after seeing scores.
        wanted = directions*allowed
        pair = tape.pairs[day]
        eligible = (wanted != 0) & (pair[:, 0] >= 0)
        if p.execution_policy == "staged":
            eligible &= pair[:, 0] > retired_front
        signature = tuple((int(pair[j, 0]), int(pair[j, 1]) if is_spread else -1, int(wanted[j]))
                          if eligible[j] else (-1, -1, 0) for j in range(len(PRODUCTS)))
        rebalance = new_month or signature != old_signature
        known_equity = equity_history.get(obs, p.capital)
        unit_sd = np.full(len(PRODUCTS), np.nan)
        active = np.flatnonzero(eligible)
        covariance = None
        unit_history = None
        risk_reason = "no_active_directions"
        if len(active):
            cache_key = (day, is_spread, tuple(active), p.unit_window, p.unit_minimum, p.covariance_window, p.covariance_minimum)
            if cache_key not in tape.risk_cache:
                lo = max(1, obs-p.covariance_window+1)
                columns = []
                for j in active:
                    series = tape.deltas[lo:obs+1, pair[j, 0]].copy()
                    if is_spread:
                        series -= tape.deltas[lo:obs+1, pair[j, 1]]
                    columns.append(series)
                history = np.column_stack(columns)
                sds = []
                for i in range(len(active)):
                    valid = history[:, i][np.isfinite(history[:, i])][-p.unit_window:]
                    sds.append(float(np.std(valid, ddof=1)) if len(valid) >= p.unit_minimum else np.nan)
                good = np.isfinite(sds) & (np.array(sds) > 0)
                used = active[good]
                joint = history[:, good]
                joint = joint[np.isfinite(joint).all(axis=1)]
                cov = np.atleast_2d(np.cov(joint, rowvar=False, ddof=1)) if len(used) and len(joint) >= p.covariance_minimum else None
                tape.risk_cache[cache_key] = (used, np.asarray(sds)[good], cov, len(joint))
            active, sds, covariance, common_days = tape.risk_cache[cache_key]
            unit_sd[active] = sds
            risk_reason = "eligible" if covariance is not None else "insufficient_joint_risk_history"
        qty = np.zeros(len(PRODUCTS), dtype=float)
        if covariance is not None and known_equity > 0:
            if rebalance:
                qty[active] = wanted[active]*p.annual_risk_cap*known_equity/(np.sqrt(len(active)*252)*unit_sd[active])
            else:
                qty[active] = last_requested[active]
            forecast = float(np.sqrt(max(0, qty[active] @ covariance @ qty[active])*252))
            risk_scale = min(1., p.annual_risk_cap*known_equity/forecast) if forecast > 0 else 1.
            qty *= risk_scale
        else:
            forecast, risk_scale = 0., 0.
        # Historical gross basis uses observations through t-2 only.
        needed = set(np.flatnonzero(positions))
        for j in np.flatnonzero(qty):
            needed.add(int(pair[j, 0]))
            if is_spread:
                needed.add(int(pair[j, 1]))
        price_basis = np.zeros(len(c))
        for key in sorted(needed):
            past = prices[:obs+1, key]
            valid = np.abs(past[np.isfinite(past)])[-p.unit_window:]
            price_basis[key] = float(max(valid[-1], np.median(valid))) if len(valid) else abs(marks[key])
        frozen_target = np.zeros(len(c), dtype=float)
        for j in np.flatnonzero(qty):
            frozen_target[pair[j, 0]] += qty[j]
            if is_spread:
                frozen_target[pair[j, 1]] -= qty[j]
        gross_before = float(np.sum(np.abs(frozen_target)*multipliers*price_basis))
        cost_per_unit = p.commission+p.slippage_ticks*ticks*multipliers
        fee_budget = float(np.sum(np.abs(frozen_target-positions)*cost_per_unit))
        budget = max(0, known_equity-fee_budget)
        funding_scale = min(1., p.gross_limit*budget/gross_before, p.reserve_limit*budget/(reserve_rate*gross_before)) if gross_before > 0 else 1.
        continuous_qty = qty*funding_scale
        integer_qty = np.trunc(continuous_qty).astype(np.int64)
        last_requested = integer_qty.copy()
        target = np.zeros(len(c), dtype=np.int64)
        for j in np.flatnonzero(integer_qty):
            target[pair[j, 0]] += integer_qty[j]
            if is_spread:
                target[pair[j, 1]] -= integer_qty[j]
        margin_scale = 1.
        if stress is not None:
            known_gross = float(np.sum(np.abs(positions)*multipliers*price_basis))
            if known_gross > 0:
                margin_scale = min(1., p.reserve_limit*max(0,known_equity)/(reserve_rate*known_gross))
            if margin_scale < 1:
                # Announced current reserve rate + lagged value, before today's
                # price or offered capacity. No new risk until buffer restored.
                target = np.sign(positions)*np.trunc(np.abs(positions)*margin_scale).astype(np.int64)
                events.append(dict(session=dates[day].date().isoformat(),product="PORTFOLIO",code="proxy_margin_reduction_requested",detail=f"rate={reserve_rate}; scale={margin_scale}"))
        slice_target = positions.copy()
        if p.execution_policy == "staged":
            # Freeze paired slices BEFORE today's reference or activity is seen.
            for j, product in enumerate(PRODUCTS):
                group = product_indices[j]
                held = group[positions[group] != 0]
                if not len(held):
                    pending[j] = False
                    continue
                remaining = int(np.min(tape.deadlines[held])-day+1)
                history = tape.volume[max(0, obs-p.capacity_window+1):obs+1, held]
                conservative = int(np.floor(p.participation*history).min()) if len(history) == p.capacity_window and np.isfinite(history).all() else 0
                if stress is not None:
                    history = observed_capacity[max(0,obs-p.capacity_window+1):obs+1,held]
                    conservative = int(history.min()) if len(history)==p.capacity_window and np.isfinite(history).all() else 0
                units = int(np.abs(positions[held]).max())
                drain_days = int(np.ceil(units/conservative)) if conservative > 0 else np.inf
                early = p.exit_lead > 0 and (remaining <= p.exit_lead or remaining <= drain_days+p.drain_buffer or conservative == 0)
                if early:
                    if retired_front[j] < held.min():
                        events.append(dict(session=dates[day].date().isoformat(), product=product, code="early_retirement_started", detail=f"remaining={remaining}; conservative_capacity={conservative}; units={units}"))
                    retired_front[j] = max(retired_front[j], int(held.min()))
                    pending[j] = True
                    exit_goals[group] = 0
                    target[group] = 0
                    continuous_qty[j], integer_qty[j], last_requested[j] = 0., 0, 0
                old, new = positions[group], target[group]
                old_keys, new_keys = np.flatnonzero(old), np.flatnonzero(new)
                replacing = (not np.array_equal(old_keys, new_keys)
                             or (np.sign(old[old_keys]) != np.sign(new[old_keys])).any())
                goal = np.zeros(len(group), dtype=np.int64) if replacing else np.sign(old)*np.minimum(np.abs(old), np.abs(new))
                if pending[j]:
                    exit_goals[group] = np.sign(old)*np.minimum(np.abs(exit_goals[group]), np.abs(goal))
                elif (goal != old).any():
                    pending[j] = True
                    exit_goals[group] = goal
                if pending[j]:
                    reductions = np.abs(old-exit_goals[group])
                    changed = group[reductions > 0]
                    required = int(reductions.max())
                    activity = tape.volume[obs, changed]
                    capacity = int(np.floor(p.participation*activity).min()) if len(changed) and np.isfinite(activity).all() else 0
                    if stress is not None:
                        activity = observed_capacity[obs,changed]
                        capacity = int(activity.min()) if len(changed) and np.isfinite(activity).all() else 0
                    planned = min(required, capacity)
                    slice_target[group] = old-np.sign(old)*np.minimum(reductions, planned)
                    exit_plans.append(dict(session=dates[day].date().isoformat(), observation=dates[obs].date().isoformat(),
                                           product=product, contracts=";".join(keys[held]), held_units=units,
                                           required_units=required, planned_units=planned, current_capacity=capacity,
                                           conservative_capacity=conservative, remaining_sessions=remaining, early_retirement=early,
                                           goal_units=int(np.abs(exit_goals[group]).max()), retired_near="" if retired_front[j] < 0 else keys[retired_front[j]]))
                if stress is not None:
                    actual_limit = np.minimum(observed_capacity[obs,held],np.floor(np.floor(p.participation*tape.volume[obs,held])*stress.capacity_factor[day,held]))
                    offered = int(actual_limit.min()) if np.isfinite(actual_limit).all() else 0
                    stress_budgets.append(dict(session=dates[day].date().isoformat(),observation=dates[obs].date().isoformat(),
                        product=product,contracts=";".join(keys[held]),held_units=units,conservative_capacity=conservative,
                        offered_capacity=offered,remaining_sessions=remaining,
                        required_drain_sessions=drain_days if np.isfinite(drain_days) else np.nan,
                        budget_slack=remaining-drain_days-p.drain_buffer if np.isfinite(drain_days) else np.nan,
                        no_projected_capacity=conservative==0,current_shock=bool((stress.capacity_factor[day,held]<1).any()),
                        margin_factor=stress.margin_factor[day]))
        open_target = target.copy()
        if p.entry_budget:
            for j, product in enumerate(PRODUCTS):
                group = product_indices[j]
                old, new = positions[group], target[group]
                adding = (np.abs(new) > np.abs(old)).any() or ((old*new) < 0).any()
                if stress is not None:
                    after_reduction = slice_target[group]
                    adding |= (np.abs(new)>np.abs(after_reduction)).any() or ((after_reduction*new)<0).any()
                if not adding:
                    continue
                candidate = group[new != 0]
                history = tape.volume[max(0, obs-p.capacity_window+1):obs+1, candidate]
                capacity = int(np.floor(p.participation*history).min()) if len(history) == p.capacity_window and np.isfinite(history).all() else 0
                if stress is not None:
                    history = observed_capacity[max(0,obs-p.capacity_window+1):obs+1,candidate]
                    capacity = int(history.min()) if len(history)==p.capacity_window and np.isfinite(history).all() else 0
                remaining = int(np.min(tape.deadlines[candidate])-day)
                assessment = _entry_budget(int(np.abs(new).max()), capacity, remaining, p.exit_lead, p.drain_buffer)
                admissions.append(dict(session=dates[day].date().isoformat(), observation=dates[obs].date().isoformat(),
                                       product=product, contracts=";".join(keys[candidate]),
                                       current_units=int(np.abs(old).max()), deadline=dates[int(np.min(tape.deadlines[candidate]))].date().isoformat(),
                                       paired=is_spread, **assessment))
                if not assessment["admitted"]:
                    # Preserve the frozen reduction result; do not restore old
                    # exposure after its close or interfere with pending exits.
                    open_target[group] = slice_target[group]
                    events.append(dict(session=dates[day].date().isoformat(), product=product, code="entry_refused_exit_budget", detail=assessment["reason"]))
        old_signature = signature
        decision_at = (dates[day]+pd.Timedelta(hours=7)).tz_localize("America/Chicago").tz_convert("UTC").isoformat()
        for j, product in enumerate(PRODUCTS) if detail else []:
            decisions.append(dict(session=dates[day].date().isoformat(), observation=dates[obs].date().isoformat(),
                                  decision_at=decision_at, product=product, direction=wanted[j],
                                  near="" if pair[j, 0] < 0 else keys[pair[j, 0]],
                                  far="" if pair[j, 1] < 0 else keys[pair[j, 1]],
                                  continuous_units=continuous_qty[j], requested_units=int(integer_qty[j]),
                                  known_equity=known_equity, unit_sd=unit_sd[j], forecast_before=forecast,
                                  risk_scale=risk_scale, funding_scale=funding_scale, risk_reason=risk_reason,
                                  signal_month="" if score is None else score.iloc[j]["month"], reallocation=rebalance))
        opening, vm, fees = cash, 0., 0.
        stale = []
        for key in np.flatnonzero(positions):
            if np.isfinite(prices[day, key]):
                change = positions[key]*multipliers[key]*(prices[day, key]-marks[key])
                vm += change
                if detail:
                    pnl.append(dict(session=dates[day].date().isoformat(), product=contract_products[key], contract=keys[key],
                                    quantity=int(positions[key]), previous_mark=marks[key], mark=prices[day, key], variation_margin=change))
                marks[key] = prices[day, key]
            else:
                stale.append(int(key))
                events.append(dict(session=dates[day].date().isoformat(), product=contract_products[key], code="stale_mark", detail=keys[key]))
        cash += vm
        if cash <= 0:
            status = "failed_nonpositive_equity"
            events.append(dict(session=dates[day].date().isoformat(), product="PORTFOLIO", code=status, detail="No replenishment or percentage-return continuation"))
        else:
            reduction = positions.copy()
            if p.execution_policy == "exit_first":
                for group in product_indices:
                    old, new = positions[group], target[group]
                    old_keys = np.flatnonzero(old)
                    new_keys = np.flatnonzero(new)
                    replacing = (not np.array_equal(old_keys, new_keys)
                                 or (np.sign(old[old_keys]) != np.sign(new[old_keys])).any())
                    reduction[group] = 0 if replacing else np.sign(old)*np.minimum(np.abs(old), np.abs(new))
            elif p.execution_policy == "staged":
                reduction = slice_target
            # All exits precede ALL additions, avoiding product-order funding
            # dependence. Closing an old spread remains a single atomic basket.
            stages = [("coupled", target)] if p.execution_policy == "coupled" else [("reduce", reduction), ("open", open_target)]
            used_capacity = np.zeros(len(c), dtype=np.int64)
            blocked = set()
            for stage, stage_target in stages:
                for j, product in enumerate(PRODUCTS):
                    group = product_indices[j]
                    if stage == "open" and p.execution_policy == "staged" and pending[j]:
                        if (positions[group] != exit_goals[group]).any():
                            events.append(dict(session=dates[day].date().isoformat(), product=product, code="entry_blocked_by_pending_reduction", detail="Latched paired exit goal not reached"))
                            continue
                        pending[j] = False
                    if stage == "open" and j in blocked:
                        events.append(dict(session=dates[day].date().isoformat(), product=product, code="entry_blocked_by_unfilled_exit", detail="Old risk retained; replacement not attempted"))
                        continue
                    changes = stage_target[group]-positions[group]
                    changed = group[changes != 0]
                    if not len(changed):
                        continue
                    delta = stage_target[changed]-positions[changed]
                    effective_target = stage_target[group]
                    available = np.floor(p.participation*tape.volume[obs,changed])
                    if stress is not None:
                        available = np.minimum(observed_capacity[obs,changed],np.floor(available*stress.capacity_factor[day,changed]))
                        if stage == "reduce" and np.isfinite(available).all():
                            feasible = max(0,int((available-used_capacity[changed]).min()))
                            actual_units = min(int(np.abs(delta).min()),feasible)
                            if actual_units > 0:
                                delta = np.sign(delta)*actual_units
                                effective_target = positions[group].copy()
                                effective_target[np.flatnonzero(changes)] += delta
                    failure = ""
                    if not np.isfinite(available).all() or (np.abs(delta)+used_capacity[changed] > available).any():
                        failure = "lagged_participation_limit" if stress is None else "stressed_shared_capacity_limit"
                    elif not np.isfinite(prices[day, changed]).all():
                        failure = "missing_execution_reference"
                    elif not np.isfinite(tape.volume[day, changed]).all() or (tape.volume[day, changed] <= 0).any():
                        failure = "zero_or_missing_execution_activity"
                    candidate = positions.copy()
                    candidate[group] = effective_target
                    cost = float(np.sum(np.abs(delta)*cost_per_unit[changed]))
                    candidate_marks = marks.copy()
                    candidate_marks[changed] = prices[day, changed]
                    gross = float(np.nansum(np.abs(candidate)*multipliers*np.maximum(np.abs(candidate_marks), price_basis)))
                    increasing = (np.abs(effective_target) > np.abs(positions[group])).any()
                    if cash-cost <= 0 or (increasing and gross > min(p.gross_limit, p.reserve_limit/reserve_rate)*(cash-cost)):
                        failure = "post_mark_funding_limit"
                    if stale and increasing:
                        failure = "increasing_risk_with_stale_marks"
                    if failure:
                        code = "unfilled_basket" if stage == "coupled" else "unfilled_"+stage+"_basket"
                        events.append(dict(session=dates[day].date().isoformat(), product=product, code=code, detail=failure))
                        if stage == "reduce":
                            blocked.add(j)
                    else:
                        for key, change in zip(changed, delta):
                            trades.append(dict(session=dates[day].date().isoformat(), product=product, contract=keys[key],
                                               delta=int(change), reference=prices[day, key], multiplier=multipliers[key],
                                               commission=abs(change)*p.commission, slippage=abs(change)*p.slippage_ticks*ticks[key]*multipliers[key],
                                               cost=abs(change)*cost_per_unit[key]))
                        if stage != "coupled":
                            events.append(dict(session=dates[day].date().isoformat(), product=product, code="filled_"+stage+"_basket", detail=";".join(keys[changed])))
                        used_capacity[changed] += np.abs(delta)
                        cash -= cost
                        fees += cost
                        positions, marks = candidate, candidate_marks
        held = np.flatnonzero(positions)
        if (day >= tape.deadlines[held]).any():
            status = "failed_known_boundary_exit"
            for key in held[day >= tape.deadlines[held]]:
                events.append(dict(session=dates[day].date().isoformat(), product=contract_products[key], code=status, detail=keys[key]))
        gross = float(np.nansum(np.abs(positions)*multipliers*np.maximum(np.abs(marks), price_basis)))
        reserve = reserve_rate*gross
        if gross > p.gross_limit*cash or reserve > p.reserve_limit*cash:
            events.append(dict(session=dates[day].date().isoformat(), product="PORTFOLIO", code="constraint_breach", detail="Reduction requested at next feasible decision"))
        if stress is not None:
            shortfall = max(0.,reserve-cash)
            stress_sessions.append(dict(session=dates[day].date().isoformat(),reserve_rate=reserve_rate,
                margin_factor=stress.margin_factor[day],margin_target_scale=margin_scale,
                risk_buffer_breach=reserve>p.reserve_limit*cash,collateral_shortfall=shortfall,
                shocked_held_contracts=int((stress.capacity_factor[day,held]<1).sum()),
                all_shocked_contracts=int((stress.capacity_factor[day]<1).sum())))
            if shortfall > 0:
                events.append(dict(session=dates[day].date().isoformat(),product="PORTFOLIO",code="failed_proxy_collateral_shortfall",detail=f"reserve={reserve}; cash={cash}; no external top-up"))
                if not status.startswith("failed"):
                    status = "failed_proxy_collateral_shortfall"
        for key in held if detail else []:
            holdings.append(dict(session=dates[day].date().isoformat(), product=contract_products[key], contract=keys[key], quantity=int(positions[key]), mark=marks[key], multiplier=multipliers[key], stale=key in stale))
        ledger.append(dict(session=dates[day].date().isoformat(), opening_equity=opening, variation_margin=vm, costs=fees, equity=cash,
                           gross_proxy=gross, reserve=reserve, free_cash=cash-reserve, positions=len(held), stale_contracts=len(stale), status=status))
        equity_history[day] = cash
        if status.startswith("failed"):
            break
    ledger = pd.DataFrame(ledger)
    trades = pd.DataFrame(trades, columns=["session", "product", "contract", "delta", "reference", "multiplier", "commission", "slippage", "cost"])
    # Independent telescoping check, including marked OPEN contracts at sample end.
    trade_bridge = -float((trades.delta*trades.reference*trades.multiplier).sum())
    terminal = float(np.nansum(positions*marks*multipliers))
    independent_equity = p.capital+trade_bridge+terminal-trades.cost.sum()
    reconciliation = dict(independent_terminal_equity=independent_equity, ledger_terminal_equity=cash,
                          terminal_error=float(independent_equity-cash),
                          maximum_daily_error=float((ledger.equity-ledger.opening_equity-ledger.variation_margin+ledger.costs).abs().max()),
                          positions_at_end=int(np.count_nonzero(positions)))
    if not np.isclose(independent_equity, cash, atol=1e-6, rtol=0):
        raise AssertionError("independent futures cash reconciliation failed")
    if not len(trades) and not status.startswith("failed"):
        status = "completed_no_qualified_trades"
    result = dict(strategy=strategy, status=status, protocol=asdict(p), ledger=ledger, trades=trades,
                decisions=pd.DataFrame(decisions), holdings=pd.DataFrame(holdings),
                pnl=pd.DataFrame(pnl, columns=["session", "product", "contract", "quantity", "previous_mark", "mark", "variation_margin"]),
                events=pd.DataFrame(events, columns=["session", "product", "code", "detail"]), reconciliation=reconciliation)
    if p.execution_policy == "staged":
        result["exit_plans"] = pd.DataFrame(exit_plans, columns=["session", "observation", "product", "contracts", "held_units", "required_units", "planned_units", "current_capacity", "conservative_capacity", "remaining_sessions", "early_retirement", "goal_units", "retired_near"])
    if p.entry_budget:
        result["entry_admissions"] = pd.DataFrame(admissions, columns=["session", "observation", "product", "contracts", "current_units", "deadline", "paired", "target_units", "conservative_capacity", "remaining_exit_sessions", "required_drain_sessions", "lead_ok", "drain_ok", "admitted", "reason"])
    if stress is not None:
        result["stress_budgets"] = pd.DataFrame(stress_budgets)
        result["stress_sessions"] = pd.DataFrame(stress_sessions)
    return result
