"""Capture the fixed five-ETF 2009–2025 reference privately; never shorten it."""
import argparse
from datetime import datetime,timezone
import importlib.metadata
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
import yfinance as yf
from strategy_lab.allocation.config import ASSETS
from strategy_lab.allocation.data import validate_prices
from strategy_lab.allocation.report import sha256,write_csv,write_json
from strategy_lab.runtime import require_empty_output


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();destination=args.output.resolve()
    if destination.is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError("Capture must stay outside public repository")
    out=require_empty_output(destination)
    receipt={"status":"pending","data_kind":"private-real-current-vintage","assets":list(ASSETS),
             "source":"Yahoo Finance adjusted closes through yfinance; personal research reference",
             "requested_start":"2009-01-01","requested_end_inclusive":"2025-12-31",
             "retrieved_utc":datetime.now(timezone.utc).isoformat(),
             "packages":{p:importlib.metadata.version(p) for p in ["yfinance","exchange-calendars"]},
             "calendar":"XNYS current historical schedule; not original release archive",
             "rights":"Real inputs and all derived real reports remain private; no redistribution permission inferred",
             "vintage":"Current adjusted history, not archived original historical releases"}
    try:
        dates=pd.DatetimeIndex(xcals.get_calendar("XNYS",start="2009-01-01",end="2025-12-31").sessions)
        if dates.tz is not None:dates=dates.tz_localize(None)
        write_csv(out/"sessions.csv",pd.DataFrame({"date":dates}));rows=[]
        for asset in ASSETS:
            print("Requesting full history: "+asset,flush=True)
            raw=yf.download(asset,start="2009-01-01",end="2026-01-01",auto_adjust=False,actions=False,
                            progress=False,threads=False,timeout=30)
            if raw.empty:raise ValueError(asset+": empty provider response")
            raw.to_csv(out/(asset+"_provider.csv"),lineterminator="\n")
            values=raw["Adj Close"]
            if isinstance(values,pd.DataFrame):values=values[asset]
            index=pd.DatetimeIndex(values.index)
            if index.tz is not None:index=index.tz_localize(None)
            rows.append(pd.DataFrame({"date":index,"ticker":asset,"adjusted_close":values.to_numpy()}))
        frame=validate_prices(pd.concat(rows,ignore_index=True).sort_values(["date","ticker"]).reset_index(drop=True),dates)
        write_csv(out/"prices.csv",frame)
        receipt.update(status="complete",sessions=len(dates),rows=len(frame),prices_sha256=sha256(out/"prices.csv"),
                       sessions_sha256=sha256(out/"sessions.csv"),provider_sha256={a:sha256(out/(a+"_provider.csv")) for a in ASSETS})
    except Exception as error:
        receipt.update(status="failed",reason=f"{type(error).__name__}: {error}");write_json(out/"source.json",receipt);raise
    write_json(out/"source.json",receipt)
    print("Complete common sessions: "+str(len(dates)),flush=True)


if __name__=="__main__":main()
