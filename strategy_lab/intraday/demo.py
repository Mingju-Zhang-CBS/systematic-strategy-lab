"""Invented paths deliberately exercise both fills and failures."""
import numpy as np
import pandas as pd


def fixture(days=42):
    rng = np.random.default_rng(20261030)
    bars, quotes = [], []
    price = 100.
    for i, date in enumerate(pd.bdate_range("2023-01-03", periods=days)):
        opened = pd.Timestamp(str(date.date())+" 09:30", tz="America/New_York").tz_convert("UTC")
        closed = opened+pd.Timedelta(hours=6.5)
        gap = rng.normal(0,.003)
        opening = price*(1+gap)
        for k in range(1,14):
            end = opened+pd.Timedelta(minutes=30*k)
            price = opening*(1+.002*np.sin(k+i)+.0015*(k/13)*(1 if i%2 else -1))
            volume = 100000.
            bars.append({"asset": "SYNTH", "bar_end": end, "session_open": opened,
                         "session_close": closed, "close": price, "volume": volume,
                         "dollar_volume": volume*(price+opening)/2, "open_price": opening,
                         "cash_dividend": 0., "split": 1.})
            if k < 13:
                for latency in [1,60]:
                    t = end+pd.Timedelta(seconds=latency)
                    mid = price+(.02 if latency == 60 else 0)
                    quotes.append({"asset":"SYNTH", "quote_time":t, "bid":mid-.01,
                                   "ask":mid+.01, "bid_size":5000, "ask_size":5000, "condition":"R"})
        for latency in [1,60]:
            quotes.append({"asset":"SYNTH", "quote_time":closed-pd.Timedelta(seconds=60-latency),
                           "bid":price-.01, "ask":price+.01, "bid_size":5000, "ask_size":5000, "condition":"R"})
    return pd.DataFrame(bars), pd.DataFrame(quotes).sort_values("quote_time").reset_index(drop=True)
