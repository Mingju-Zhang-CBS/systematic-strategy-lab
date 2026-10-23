"""Portable manifests and sampled process memory; no absolute paths are recorded."""
from __future__ import annotations
import hashlib, importlib.metadata, json, platform, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
import psutil

class Measurement:
    """Sample absolute process RSS every 10ms; not a native allocation profiler."""
    def __enter__(self):
        self.process = psutil.Process()
        self.start_rss = self.peak = self.process.memory_info().rss
        self.done = threading.Event()
        self.start = time.perf_counter()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self
    def sample(self):
        while not self.done.wait(.01):
            self.peak = max(self.peak, self.process.memory_info().rss)
    def __exit__(self, *args):
        self.peak = max(self.peak, self.process.memory_info().rss)
        self.done.set(); self.thread.join()
        self.result = {"seconds": time.perf_counter()-self.start,
                       "sampled_peak_rss_mb": self.peak/1024**2,
                       "rss_increase_mb": max(0,self.peak-self.start_rss)/1024**2}

def source_hashes():
    root = Path(__file__).resolve().parent
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))}

def manifest(config, data_hash, kind):
    names = ["numpy","pandas","scipy","scikit-learn","lightgbm","catboost","matplotlib","psutil"]
    versions = {}
    for name in names:
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: pass
    return {"generated_utc":datetime.now(timezone.utc).isoformat(),"data_kind":kind,
            "input_sha256":data_hash,"configuration":config,"source_sha256":source_hashes(),
            "environment":{"python":platform.python_version(),"os":platform.system(),
                           "machine":platform.machine(),"packages":versions},
            "measurement_note":"Wall time and process RSS sampled every 10ms; timing is machine-specific; brief peaks may be missed."}

def dump(path, obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding="utf-8")

def require_empty_output(path):
    path=Path(path)
    if path.exists() and any(path.iterdir()):
        raise ValueError("Output directory is nonempty; use a new directory or explicitly remove the old generated run.")
    path.mkdir(parents=True,exist_ok=True)
    return path
