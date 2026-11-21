"""Run the pipeline on a KIO half (dev|test) and score against gold v2.  python -m eval.run_kio dev --profile standard"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("half", choices=["dev", "test"])
    ap.add_argument("--profile", default=None)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--details", action="store_true", help="print per-field errors (dev only!)")
    a = ap.parse_args()
    tag = time.strftime("%H%M%S") + "_" + (a.profile or "default")
    out = ROOT / "runs" / f"kio_{a.half}_{tag}"
    cmd = [sys.executable, str(ROOT / "run.py"), "--input", str(ROOT / "runs/kio_input" / a.half),
           "--output", str(out / "output"), "--trace", str(out / "trace"), "--workers", str(a.workers)]
    if a.profile:
        cmd += ["--profile", a.profile]
    t0 = time.time()
    log = subprocess.run(cmd, capture_output=True, text=True)
    from eval.score import score_dirs
    show = a.details and a.half == "dev"
    r = score_dirs(out / "output", ROOT / "runs/kio_gold2" / a.half, verbose=show)
    import re
    cost = re.findall(r"cost=\$([0-9.]+)", log.stdout)
    print(f"KIO {a.half} profile={a.profile or 'default'}  F1={r['f1']:.4f}  {r['counts']}  "
          f"time={time.time() - t0:.0f}s  out={out}")
    print("per doc type:", {k: v for k, v in sorted(r["per_field"].items())[:0]}, end="")
    by = {}
    for k, v in r["per_field"].items():
        t = k.split(":")[0]
        for x in ("TP", "FP", "FN"):
            by.setdefault(t, {"TP": 0, "FP": 0, "FN": 0})[x] += v.get(x, 0)
    print({t: round(2 * c["TP"] / max(1, 2 * c["TP"] + c["FP"] + c["FN"]), 4) for t, c in by.items()})


if __name__ == "__main__":
    main()
