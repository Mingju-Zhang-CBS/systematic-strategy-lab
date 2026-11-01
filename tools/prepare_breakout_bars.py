"""Privately derive OHLC from the exact archived parent HMM capture, without refresh."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd
from strategy_lab.regimes.breakout.data import validate_bars
from strategy_lab.regimes.breakout.reference import sha256,closes_hash
from strategy_lab.runtime import require_empty_output


def write_json(path,obj):path.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")


def derive(capture,parent,output):
    capture=Path(capture);parent=Path(parent);output=Path(output).resolve()
    if output.is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError("Real bars must remain outside public repository")
    out=require_empty_output(output)
    receipt={"status":"pending","data_kind":"private-real-current-vintage","prepared_utc":datetime.now(timezone.utc).isoformat(),
             "source":"hash-verified archived parent HMM Yahoo capture; no new download",
             "adjustment":"factor=exact parent analyzed adjusted close / archived provider raw close; scale open/high/low by factor",
             "parent_parse":"Match parent analysis pandas default close parsing; new bars use round-trip parsing",
             "rights":"Real OHLC, fitted parameters and all derived real findings stay private",
             "vintage":"Same parent capture vintage; adjustment is not a historical release archive or executable quote"}
    try:
        original=json.loads((capture/"source.json").read_text(encoding="utf-8"))
        manifest=json.loads((parent/"manifest.json").read_text(encoding="utf-8"))
        if original["status"]!="complete" or original["data_kind"]!="private-real-current-vintage":raise ValueError("Completed parent capture required")
        if sha256(capture/"prices.csv")!=original["prices_sha256"] or manifest["input_sha256"]!=original["prices_sha256"]:
            raise ValueError("Archived close binding differs")
        if sha256(capture/"sessions.csv")!=original["sessions_sha256"]:raise ValueError("Archived session calendar differs")
        closes=pd.read_csv(capture/"prices.csv",parse_dates=["date"])
        sessions=pd.read_csv(capture/"sessions.csv",parse_dates=["date"])
        rows=[];roundoff={}
        for asset in ("SPY","QQQ"):
            path=capture/(asset+"_provider.csv")
            if sha256(path)!=original["provider_sha256"][asset]:raise ValueError("Provider archive fingerprint differs")
            raw=pd.read_csv(path,header=[0,1],skiprows=[2],index_col=0,parse_dates=True)
            raw=raw.xs(asset,axis=1,level=1)
            selected=closes[closes.ticker.eq(asset)].set_index("date")
            if not raw.index.equals(selected.index):raise ValueError("Provider sessions differ from analyzed closes")
            if not np.isfinite(raw[["Open","High","Low","Close","Adj Close"]].to_numpy()).all():raise ValueError("Incomplete archived OHLC")
            mismatch=np.abs(raw["Adj Close"].to_numpy()/selected.adjusted_close.to_numpy()-1)
            if mismatch.max()>1e-12:raise ValueError("Provider and parent adjusted closes differ beyond parsing roundoff")
            factor=selected.adjusted_close/raw["Close"]
            frame=selected.copy()
            for field,raw_name in [("adjusted_open","Open"),("adjusted_high","High"),("adjusted_low","Low")]:
                frame[field]=(raw[raw_name]*factor).to_numpy()
            frame=frame.reset_index();rows.append(frame)
            roundoff[asset]=float(mismatch.max())
        bars=validate_bars(pd.concat(rows,ignore_index=True).sort_values(["date","ticker"]).reset_index(drop=True),sessions.date)
        bars.to_csv(out/"bars.csv",index=False,float_format="%.17g",lineterminator="\n")
        (out/"sessions.csv").write_bytes((capture/"sessions.csv").read_bytes())
        reread=pd.read_csv(out/"bars.csv",parse_dates=["date"],float_precision="round_trip")
        if not np.array_equal(reread.adjusted_close.to_numpy(),bars.adjusted_close.to_numpy()):raise ValueError("Round-trip close preservation failed")
        receipt.update(status="complete",sessions=len(sessions),rows=len(bars),bars_sha256=sha256(out/"bars.csv"),
                       sessions_sha256=sha256(out/"sessions.csv"),parent_prices_sha256=original["prices_sha256"],
                       analyzed_closes_sha256=closes_hash(bars),parent_manifest_sha256=sha256(parent/"manifest.json"),
                       parent_capture_sha256=sha256(capture/"source.json"),parent_capture_utc=original["retrieved_utc"],
                       provider_sha256=original["provider_sha256"],maximum_relative_parse_difference=roundoff)
    except Exception as error:
        receipt.update(status="failed",reason=f"{type(error).__name__}: {error}");write_json(out/"source.json",receipt);raise
    write_json(out/"source.json",receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("capture","parent","output"):parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args();receipt=derive(args.capture,args.parent,args.output)
    print(f"Prepared {receipt['sessions']} sessions from the same parent capture; analyzed closes unchanged")


if __name__=="__main__":main()
