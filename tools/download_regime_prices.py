"""Private Yahoo adjusted-close capture for the frozen 2009–2025 study.

Install the regimes and regimes-download extras. Keep the output outside the
public repository. A failed capture writes a receipt rather than shortening dates.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import pandas as pd
import exchange_calendars as xcals
import yfinance as yf
from strategy_lab.regimes.data import validate_prices
from strategy_lab.regimes.report import sha256, write_csv, write_json
from strategy_lab.runtime import require_empty_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    public_root = Path(__file__).resolve().parents[1]
    if destination.is_relative_to(public_root):
        raise ValueError("Real capture must be outside the public repository")
    out = require_empty_output(destination)
    receipt = {"status": "pending", "data_kind": "private-real-current-vintage",
               "source": "Yahoo Finance adjusted closes through yfinance; personal research only",
               "retrieved_utc": datetime.now(timezone.utc).isoformat(),
               "requested_start": "2009-01-01", "requested_end_inclusive": "2025-12-31",
               "yfinance": importlib.metadata.version("yfinance"),
               "exchange_calendars": importlib.metadata.version("exchange-calendars"),
               "calendar": "XNYS current historical schedule; not original publication archive",
               "rights_status": "No public redistribution of inputs or derived real reports authorized",
               "vintage_limitation": "Adjusted history downloaded now; original release vintages unavailable"}
    try:
        calendar = xcals.get_calendar("XNYS", start="2009-01-01", end="2025-12-31")
        # Jan 1 is a holiday, outside this calendar's first valid session.
        sessions = pd.DatetimeIndex(calendar.sessions)
        if sessions.tz is not None:
            sessions = sessions.tz_localize(None)
        write_csv(out/"sessions.csv", pd.DataFrame({"date": sessions}))
        rows = []
        for ticker in ("SPY", "QQQ"):
            print(f"Requesting {ticker}, complete 2009–2025", flush=True)
            raw = yf.download(ticker, start="2009-01-01", end="2026-01-01", auto_adjust=False,
                              actions=False, progress=False, threads=False, timeout=30)
            if raw.empty:
                raise ValueError(f"{ticker}: provider returned no observations")
            # Keep the complete response private, including the provider's raw/adjusted distinction.
            raw.to_csv(out/f"{ticker}_provider.csv", lineterminator="\n")
            close = raw["Adj Close"]
            if isinstance(close, pd.DataFrame):
                close = close[ticker]
            dates = pd.DatetimeIndex(close.index)
            if dates.tz is not None:
                dates = dates.tz_localize(None)
            rows.append(pd.DataFrame({"date": dates, "ticker": ticker, "adjusted_close": close.to_numpy()}))
        frame = pd.concat(rows, ignore_index=True).sort_values(["date", "ticker"]).reset_index(drop=True)
        frame = validate_prices(frame, sessions)
        write_csv(out/"prices.csv", frame)
        receipt.update(status="complete", rows=len(frame), sessions=len(sessions),
                       prices_sha256=sha256(out/"prices.csv"), sessions_sha256=sha256(out/"sessions.csv"),
                       provider_sha256={t: sha256(out/f"{t}_provider.csv") for t in ("SPY", "QQQ")})
    except Exception as error:
        receipt.update(status="failed", reason=f"{type(error).__name__}: {error}")
        write_json(out/"source.json", receipt)
        raise
    write_json(out/"source.json", receipt)
    print(f"Saved {receipt['sessions']} common sessions; real inputs remain private", flush=True)


if __name__ == "__main__":
    main()
