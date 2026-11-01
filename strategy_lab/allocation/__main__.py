"""python -m strategy_lab.allocation --demo --output local-runs/allocation"""
import argparse
import json
from pathlib import Path
import pandas as pd
from .data import synthetic_prices,validate_prices
from .report import run_study,sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo",action="store_true");mode.add_argument("--prices",type=Path)
    parser.add_argument("--sessions",type=Path);parser.add_argument("--source",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.demo:
        if args.source or args.sessions:parser.error("Demo generates its own source")
        run_study(synthetic_prices(),args.output)
    else:
        if not args.source or not args.sessions:parser.error("Real prices require --sessions and --source")
        # Source and all derived real results must remain outside this repository.
        public_root=Path(__file__).resolve().parents[2]
        if args.output.resolve().is_relative_to(public_root):raise ValueError("Real output must be outside public repository")
        receipt=json.loads(args.source.read_text(encoding="utf-8"))
        if receipt.get("status")!="complete" or receipt.get("data_kind")!="private-real-current-vintage":raise ValueError("Complete private real receipt required")
        if receipt.get("prices_sha256")!=sha256(args.prices) or receipt.get("sessions_sha256")!=sha256(args.sessions):raise ValueError("Source fingerprints differ")
        sessions=pd.read_csv(args.sessions,parse_dates=["date"])
        if list(sessions.columns)!=["date"]:raise ValueError("Sessions CSV must contain exactly date")
        frame=validate_prices(pd.read_csv(args.prices),sessions.date)
        if str(frame.date.min().date())!="2009-01-02" or str(frame.date.max().date())!="2025-12-31":raise ValueError("Do not shorten frozen 2009–2025 history")
        run_study(frame,args.output,data_kind="private-real-current-vintage",source=receipt,input_hash=sha256(args.prices))


if __name__=="__main__":main()
