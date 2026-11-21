"""Evaluate on the organiser's synthetic scans (data/skany_uzp/<type>/<id>/<id>.pdf + <id>.json)."""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "data/skany_uzp")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run = ROOT / "runs" / ("skany_uzp_" + time.strftime("%Y%m%d-%H%M%S"))
    for pdf in sorted(a.src.rglob("*.pdf")):
        case = f"{pdf.parent.parent.name}_{pdf.parent.name}"
        for kind, src in (("input", pdf), ("gt", pdf.with_suffix(".json"))):
            dst = run / kind / case / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
    subprocess.run([sys.executable, str(ROOT / "run.py"), "--input", str(run / "input"), "--output", str(run / "output"),
                    "--trace", str(run / "trace"), "--workers", str(a.workers)], check=True)
    sys.path.insert(0, str(ROOT))
    from eval.score import score_dirs
    r = score_dirs(run / "output", run / "gt", verbose=True)
    by_type = {}
    for k, v in r["per_field"].items():
        pass
    print(f"\nSKANY UZP F1 = {r['f1']:.4f}  {r['counts']}")
    print("run:", run)


if __name__ == "__main__":
    main()
