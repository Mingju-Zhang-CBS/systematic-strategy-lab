"""python -m strategy_lab.regimes --demo --output local-runs/regimes"""
import argparse
import json
from pathlib import Path
import pandas as pd
from .config import RegimeConfig
from .data import synthetic_prices, validate_prices
from .report import run_study, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--prices", type=Path)
    parser.add_argument("--sessions", type=Path, help="CSV with one date column; mandatory for real inputs")
    parser.add_argument("--source", type=Path, help="Source receipt JSON; mandatory for real inputs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.demo:
        if args.sessions or args.source:
            parser.error("Demo generates its own inputs")
        run_study(synthetic_prices(), args.output)
    else:
        if not args.sessions or not args.source:
            parser.error("Real inputs require --sessions and --source")
        receipt = json.loads(args.source.read_text(encoding="utf-8"))
        if receipt.get("status") != "complete" or receipt.get("data_kind") != "private-real-current-vintage":
            raise ValueError("Complete private real-data receipt required")
        if receipt.get("prices_sha256") != sha256(args.prices) or receipt.get("sessions_sha256") != sha256(args.sessions):
            raise ValueError("Source receipt input fingerprints differ")
        expected = pd.read_csv(args.sessions, parse_dates=["date"])
        if list(expected.columns) != ["date"]:
            raise ValueError("Sessions CSV must contain exactly date")
        frame = validate_prices(pd.read_csv(args.prices), expected.date)
        if (receipt.get("requested_start") != "2009-01-01"
                or receipt.get("requested_end_inclusive") != "2025-12-31"
                or str(frame.date.min().date()) != "2009-01-02"
                or str(frame.date.max().date()) != "2025-12-31"):
            raise ValueError("The frozen 2009–2025 history cannot be shortened")
        run_study(frame, args.output, RegimeConfig(), "private-real-current-vintage", receipt, sha256(args.prices))


if __name__ == "__main__":
    main()
