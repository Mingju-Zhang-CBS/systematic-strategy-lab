"""Bind the transfer to the unchanged parent protocol, code and saved artifacts."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from ..config import RegimeConfig,SEGMENTS


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def closes_hash(frame):
    d=frame[["date","ticker","adjusted_close"]].copy()
    d["date"]=pd.to_datetime(d.date)
    return hashlib.sha256(d.to_csv(index=False,float_format="%.17g",lineterminator="\n").encode()).hexdigest()


def load_parent(path,data_kind,source=None,analysis_hash=None):
    root=Path(path)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    protocol=json.loads((root/"protocol.json").read_text(encoding="utf-8"))
    if manifest["data_kind"]!=data_kind or protocol["config"]!=RegimeConfig().to_dict():
        raise ValueError("Parent evidence type or HMM configuration differs")
    if protocol["segments"]!={k:list(v) for k,v in SEGMENTS.items()}:
        raise ValueError("Parent chronological segments differ")
    if sha256(root/"protocol.json")!=manifest["protocol_sha256"]:
        raise ValueError("Parent protocol fingerprint differs")
    current=Path(__file__).resolve().parents[1]
    for name in ("config.py","data.py","models.py","engine.py"):
        if sha256(current/name)!=manifest["source_sha256"][name]:
            raise ValueError("Frozen parent source changed: "+name)
    expected=analysis_hash if data_kind=="synthetic" else source.get("parent_prices_sha256")
    if manifest["input_sha256"]!=expected:raise ValueError("Parent input binding differs")
    if data_kind!="synthetic" and sha256(root/"manifest.json")!=source.get("parent_manifest_sha256"):
        raise ValueError("Real parent manifest binding differs")
    for name,digest in manifest["artifacts"].items():
        target=(root/name).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file() or sha256(target)!=digest:
            raise ValueError("Parent artifact missing or changed: "+name)
    return root,manifest


def compare_states(parent,asset,states,fits,snapshots):
    old=pd.read_csv(parent/asset/"state_probabilities.csv",parse_dates=["date"],float_precision="round_trip").fillna({"reason":""})
    current=states.fillna({"reason":""})
    pd.testing.assert_frame_equal(old,current,check_exact=False,atol=1e-8,rtol=1e-7)
    old_fits=pd.read_csv(parent/asset/"training_events.csv",float_precision="round_trip").fillna({"reason":""})
    pd.testing.assert_frame_equal(old_fits,fits.fillna({"reason":""}),check_exact=False,atol=1e-8,rtol=1e-7)
    old_models=json.loads((parent/asset/"model_snapshots.json").read_text(encoding="utf-8"))
    if len(old_models)!=len(snapshots):raise ValueError("Parent fitted-model count differs")
    differences=[]
    for a,b in zip(old_models,snapshots):
        for key in ("model_id","decision_date","train_start","train_end","status"):
            if a[key]!=b[key]:raise ValueError("Parent snapshot clock differs")
        for key in a["parameters"]:
            if key=="fit_warnings":continue
            av=np.asarray(a["parameters"][key],float);bv=np.asarray(b["parameters"][key],float)
            if not np.allclose(av,bv,atol=1e-8,rtol=1e-7):raise ValueError("Parent HMM parameters differ: "+key)
            differences.append(float(np.max(np.abs(av-bv))))
        np.testing.assert_allclose(a["training_tail_probability"],b["training_tail_probability"],atol=1e-8,rtol=1e-7)
    return {"asset":asset,"state_rows":len(states),"matching_fits":len(snapshots),
            "maximum_parameter_difference":max(differences,default=0.),
            "state_probability_max_difference":float(np.nanmax(np.abs(old[["p_0","p_1","p_2"]].to_numpy()-states[["p_0","p_1","p_2"]].to_numpy()))) if states.status.eq("ok").any() else 0.,
            "warning_note":"Environment warnings are retained but excluded from parameter equivalence"}


def compare_control(parent,asset,case,strategy,ledger):
    path=parent/asset/case/(strategy+"_ledger.csv")
    if not path.exists():return None
    old=pd.read_csv(path,float_precision="round_trip").fillna({"executed_decision_date":""})
    current=ledger.fillna({"executed_decision_date":""})
    pd.testing.assert_frame_equal(old,current,check_exact=False,check_dtype=False,atol=1e-6,rtol=1e-11)
    raw=ledger.to_csv(index=False,float_format="%.17g",lineterminator="\n").encode()
    return {"asset":asset,"scenario":case,"strategy":strategy,"rows":len(ledger),
            "byte_identical":raw==path.read_bytes(),"maximum_nav_difference":float(np.max(np.abs(old.nav-ledger.nav)))}
