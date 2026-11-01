"""Frozen HMM transfer: python -m strategy_lab.regimes.breakout --demo --output local-runs/breakout"""
import argparse
import json
from pathlib import Path
import pandas as pd
from .data import synthetic_bars,validate_bars
from .reference import sha256,closes_hash
from .report import run_study


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo",action="store_true");mode.add_argument("--bars",type=Path)
    parser.add_argument("--sessions",type=Path);parser.add_argument("--source",type=Path)
    parser.add_argument("--parent",type=Path,help="Completed unchanged parent HMM run; mandatory for real inputs")
    parser.add_argument("--output",required=True,type=Path);args=parser.parse_args()
    if args.demo:
        if args.sessions or args.source:parser.error("Demo generates its own inputs")
        run_study(synthetic_bars(),args.output,parent=args.parent)
    else:
        if not all((args.sessions,args.source,args.parent)):parser.error("Real inputs need --sessions, --source and --parent")
        if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
            raise ValueError("Real artifacts must stay outside the code repository")
        source=json.loads(args.source.read_text(encoding="utf-8"))
        if source.get("status")!="complete" or source.get("data_kind")!="private-real-current-vintage":raise ValueError("Complete private receipt required")
        if source.get("bars_sha256")!=sha256(args.bars) or source.get("sessions_sha256")!=sha256(args.sessions):raise ValueError("Input fingerprints differ")
        sessions=pd.read_csv(args.sessions,parse_dates=["date"])
        if list(sessions.columns)!=["date"]:raise ValueError("Exactly one date column required")
        bars=validate_bars(pd.read_csv(args.bars,float_precision="round_trip"),sessions.date)
        if str(bars.date.min().date())!="2009-01-02" or str(bars.date.max().date())!="2025-12-31":raise ValueError("Frozen history cannot be shortened")
        if source.get("analyzed_closes_sha256")!=closes_hash(bars):raise ValueError("Analyzed parent-close binding differs")
        run_study(bars,args.output,data_kind="private-real-current-vintage",source=source,parent=args.parent)


if __name__=="__main__":main()
