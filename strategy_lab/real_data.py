"""Offline, hash-bound government fund NAV facts; no network calls."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
FUNDS = ("G", "F", "C", "S", "I")
RISKY = ("F", "C", "S", "I")


def validate_nav(frame: pd.DataFrame) -> pd.DataFrame:
    """Reject rather than fill missing prices or confuse NAVs with raw closes."""
    if list(frame.columns) != ["date", *FUNDS]:
        raise ValueError("Expected only date,G,F,C,S,I accumulation NAV columns")
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="raise")
    if frame.empty or frame.date.isna().any() or frame.date.duplicated().any():
        raise ValueError("Missing or duplicate dates")
    if not frame.date.is_monotonic_increasing:
        raise ValueError("NAV rows must be strictly ordered")
    if (frame.date.dt.dayofweek > 4).any() or (frame.date != frame.date.dt.normalize()).any():
        raise ValueError("Expected weekday valuation dates, without intraday timestamps")
    values = frame[list(FUNDS)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("NAVs must be finite, positive and complete; no forward filling")
    if frame.date.diff().dt.days.max() > 7:
        raise ValueError("Suspicious gap exceeding seven calendar days")
    return frame.reset_index(drop=True)


def load_snapshot():
    raw = (DATA / "tsp_nav.csv").read_bytes()
    source = json.loads((DATA / "source.json").read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != source["dataset_sha256"]:
        raise ValueError("Published NAV snapshot hash mismatch")
    frame = validate_nav(pd.read_csv(DATA / "tsp_nav.csv"))
    if len(frame) != source["rows"]:
        raise ValueError("Published row count mismatch")
    protocol = json.loads((DATA / "protocol.json").read_text(encoding="utf-8"))
    if frame.date.iloc[-1] > pd.Timestamp(protocol["data_end"]):
        raise ValueError("Data exceed frozen research horizon")
    return frame, source, protocol
