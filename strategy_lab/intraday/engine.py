from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    lookback: int = 14
    initial_cash: float = 100000.
    delay_seconds: int = 1
    wait_seconds: int = 5
    fee_per_share: float = .0035
    slippage_per_share: float = .001
    financing_rate: float = .06
    borrow_rate: float = .03
    initial_margin_fraction: float = .5
    target_daily_vol: float = .02
    leverage_cap: float = 4.
    participation: float = .01


def validate_inputs(bars, quotes, config):
    """Single boundary validation; downstream engine consumes normalized frames."""
    b, q = bars.copy(), quotes.copy()
    for col in ["bar_end", "session_open", "session_close"]:
        b[col] = pd.to_datetime(b[col], utc=True)
    q["quote_time"] = pd.to_datetime(q["quote_time"], utc=True)
    b["session"] = b.bar_end.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    b["slot"] = b.bar_end.dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    numeric = ["close", "volume", "dollar_volume", "open_price", "cash_dividend", "split"]
    required_q = ["bid", "ask", "bid_size", "ask_size"]
    if (b.empty or q.empty or len(b.asset.unique()) != 1 or len(q.asset.unique()) != 1
            or b.asset.iloc[0] != q.asset.iloc[0] or b.duplicated(["asset", "bar_end"]).any()
            or q.duplicated(["asset", "quote_time"]).any()
            or not b.bar_end.is_monotonic_increasing or not q.quote_time.is_monotonic_increasing
            or not np.isfinite(b[numeric]).all().all() or (b[["close", "open_price", "split"]] <= 0).any().any()
            or (b[["volume", "dollar_volume"]] < 0).any().any()
            or (b.bar_end <= b.session_open).any() or (b.bar_end > b.session_close).any()
            or not 0 < config.initial_margin_fraction <= 1 or config.lookback < 2
            or min(config.initial_cash, config.delay_seconds, config.wait_seconds) <= 0
            or not 0 < config.participation <= 1):
        raise ValueError("Ordered single-asset bars, unique UTC quotes and valid configuration required")
    for _, day in b.groupby('session',sort=False):
        expected=pd.date_range(day.session_open.iloc[0]+pd.Timedelta(minutes=30),day.session_close.iloc[0],freq='30min')
        if (len(day)!=len(expected) or not np.array_equal(day.bar_end.to_numpy(),expected.to_numpy())
                or (day[['session_open','session_close','open_price','cash_dividend','split']].nunique()!=1).any()):
            raise ValueError('Incomplete or inconsistent sessions must be quarantined before evaluation')
    q["valid"] = (np.isfinite(q[required_q]).all(axis=1) & (q.bid > 0) & (q.ask >= q.bid)
                  & (q.bid_size > 0) & (q.ask_size > 0) & q.condition.isin(["R", ""]))
    return b, q


def backtest(bars, quotes, variant="vwap", config=Config()):
    if variant not in ("base", "vwap", "vol_scaled"):
        raise ValueError("Unknown declared variant")
    b, q = validate_inputs(bars, quotes, config)
    good = q.loc[q.valid]
    qt = good.quote_time.to_numpy(dtype="datetime64[ns]")
    history, daily, orders, features = [], [], [], []
    cash, position, last_mark = config.initial_cash, 0, 0.
    for session, day in b.groupby("session", sort=True):
        day = day.copy()
        opened, closed = day.session_open.iloc[0], day.session_close.iloc[0]
        eligible_history = [h for h in history if h["full_session"]][-config.lookback:]
        previous = history[-1] if history else None
        enough = len(eligible_history) == config.lookback and len(history) >= config.lookback+1
        if not enough:
            history.append({"day": day, "close": day.close.iloc[-1], "full_session": (closed-opened).total_seconds()==23400,
                            "dividend": day.cash_dividend.iloc[0], "split": day.split.iloc[0]})
            continue
        previous_cash = cash
        open_price = day.open_price.iloc[0]
        adjusted_close = previous["close"]/day.split.iloc[0]-day.cash_dividend.iloc[0]
        rets = [(history[j]["close"]+history[j]["dividend"])*history[j]["split"]/history[j-1]["close"]-1
                for j in range(len(history)-config.lookback, len(history))]
        vol = np.std(rets, ddof=1)
        leverage = min(config.leverage_cap, config.target_daily_vol/vol) if variant == "vol_scaled" and vol > 0 else 1.
        historical_volume = np.mean([h["day"].volume.sum() for h in eligible_history])
        quantity = int(min(max(cash,0)*leverage/open_price, historical_volume*config.participation))
        cumulative_volume, cumulative_value = 0., 0.
        previous_time = opened
        costs = financing = borrow = traded = 0.
        failed = 0
        end_mark = day.close.iloc[-1]
        events = [(r.bar_end, r) for r in day.itertuples() if r.bar_end < closed-pd.Timedelta(seconds=60)]
        events.append((closed-pd.Timedelta(seconds=60), None))
        for decision, row in events:
            if row is not None:
                cumulative_volume += row.volume
                cumulative_value += row.dollar_volume
                moves = [abs(float(h["day"].loc[h["day"].slot == row.slot, "close"].iloc[0])/h["day"].open_price.iloc[0]-1)
                         for h in eligible_history if (h["day"].slot == row.slot).any()]
                if len(moves) != config.lookback or cumulative_volume == 0:
                    continue
                noise = float(np.mean(moves))
                upper, lower = max(open_price, adjusted_close)*(1+noise), min(open_price, adjusted_close)*(1-noise)
                vwap = cumulative_value/cumulative_volume
                if variant == "base":
                    target = quantity if row.close > upper else -quantity if row.close < lower else position
                else:
                    target = quantity if row.close > max(upper,vwap) else -quantity if row.close < min(lower,vwap) else 0
                features.append({"session": session, "decision": decision, "upper": upper, "lower": lower,
                                 "vwap": vwap, "quantity": quantity, "vol": vol,
                                 "history_end": eligible_history[-1]["day"].bar_end.iloc[-1]})
                last_mark = row.close
                if cash+position*last_mark < abs(position)*last_mark*config.initial_margin_fraction:
                    target = 0
            else:
                target = 0
            if target == position:
                continue
            request = decision+pd.Timedelta(seconds=config.delay_seconds)
            j = np.searchsorted(qt, request.to_datetime64(), side="left")
            deadline = min(request+pd.Timedelta(seconds=config.wait_seconds), closed)
            if j == len(good) or good.iloc[j].quote_time > deadline:
                failed += 1
                orders.append({"session": session, "decision": decision, "fill_time": pd.NaT,
                               "target": target, "position": position, "shares": 0,
                               "cash": cash, "status": "missing_quote", "reason": "close" if row is None else "signal"})
                continue
            quote = good.iloc[j]
            seconds = (quote.quote_time-previous_time).total_seconds()
            finance = max(-cash, 0)*config.financing_rate*seconds/(365*86400)
            short_cost = max(-position,0)*last_mark*config.borrow_rate*seconds/(365*86400)
            cash -= finance+short_cost
            financing += finance; borrow += short_cost
            previous_time = quote.quote_time
            direction = 1 if target > position else -1
            price = quote.ask if direction == 1 else quote.bid
            depth = int(quote.ask_size if direction == 1 else quote.bid_size)
            wanted = min(abs(target-position), depth)
            # Reductions are never blocked by admission funding. A reversal first
            # consumes displayed depth closing old risk, then budgets the opening.
            reducing = min(abs(position),wanted) if position*direction < 0 else 0
            remaining = wanted-reducing
            after_reduction = position+direction*reducing
            fee = config.fee_per_share+config.slippage_per_share
            reduced_cash = cash-direction*reducing*price-reducing*fee
            equity = reduced_cash+after_reduction*(quote.bid+quote.ask)/2
            mid = (quote.bid+quote.ask)/2
            equity_cost = fee+abs(price-mid)
            affordable = max(0,int((equity-config.initial_margin_fraction*abs(after_reduction)*mid)
                                   /(config.initial_margin_fraction*mid+equity_cost)))
            opening = min(remaining, affordable)
            actual = reducing+opening
            change = direction*actual
            cash -= change*price+actual*fee
            position += change
            costs += actual*fee
            traded += actual*price
            last_mark = (quote.bid+quote.ask)/2
            orders.append({"session": session, "decision": decision, "fill_time": quote.quote_time,
                           "target": target, "position": position, "shares": change, "price": price,
                           "fee_slippage": actual*fee, "cash": cash,
                           "status": "filled" if position == target else "partial_or_budget_limited",
                           "reason": "close" if row is None else "signal"})
        seconds = max((closed-previous_time).total_seconds(),0)
        finance = max(-cash,0)*config.financing_rate*seconds/(365*86400)
        short_cost = max(-position,0)*last_mark*config.borrow_rate*seconds/(365*86400)
        cash -= finance+short_cost; financing += finance; borrow += short_cost
        provisional_equity = cash+position*end_mark
        daily.append({"session": session, "cash": cash, "equity": provisional_equity,
                      "net_pnl": provisional_equity-previous_cash, "fee_slippage": costs,
                      "financing": financing, "borrow": borrow, "traded_notional": traded,
                      "remaining_shares": position, "missing_quotes": failed,
                      "status": "complete" if position == 0 else "stopped_unclosed_risk",
                      "valuation": "cash" if position == 0 else "provisional_last_bar_mark"})
        history.append({"day": day, "close": end_mark, "full_session": (closed-opened).total_seconds()==23400,
                        "dividend": day.cash_dividend.iloc[0], "split": day.split.iloc[0]})
        if position != 0:
            break
    return pd.DataFrame(daily), pd.DataFrame(orders), pd.DataFrame(features)
