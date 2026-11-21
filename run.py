"""CLI.

  python run.py                       # ./input -> ./output (+ ./trace z dowodami ekstrakcji)
  python run.py --input X --output Y
  python run.py eval [--cases 5] [--model M]   # ewaluacja F1 na data/train (bez wycieku few-shot)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from o2j.config import load_settings  # noqa: E402
from o2j.pipeline import Pipeline, build_gt  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Odwołania2JSON — PDF -> JSON")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "eval"])
    ap.add_argument("--input", type=Path, default=ROOT / "input")
    ap.add_argument("--output", type=Path, default=ROOT / "output")
    ap.add_argument("--trace", type=Path, default=None)
    ap.add_argument("--model", default=None, help="nadpisuje model z konfiguracji")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cases", type=int, default=0, help="eval: liczba spraw (0 = wszystkie)")
    ap.add_argument("--src", type=Path, default=None, help="eval: katalog z PDF-ami (domyślnie data/train); GT zawsze z data/train")
    ap.add_argument("--mode", default=None, help="nadpisuje extraction.mode z konfiguracji (llm | deterministic)")
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)

    s = load_settings()
    pipe = Pipeline(s, model=a.model, mode=a.mode)

    if a.command == "run":
        trace = a.trace or s["paths"]["trace"]
        summary = pipe.run_dir(a.input, a.output, trace, workers=a.workers)
        unmatched = [x["file"] for x in summary if x["doctype"] == "NIEDOPASOWANY"]
        if unmatched:
            print("\nNie udało się dopasować typu dokumentu (zapisano pusty JSON {}):")
            for f in unmatched:
                print("  -", f.removesuffix(".json"))
        print(f"\nGotowe. Wyniki: {a.output}  Ślady: {trace}")
        return

    # eval on training data, excluding the evaluated case from few-shot retrieval
    from eval.score import score_dirs
    train = s["paths"]["train"]
    src = a.src or train
    cases = sorted(p.name for p in src.iterdir() if p.is_dir())
    if a.cases:
        cases = cases[:: max(1, len(cases) // a.cases)][: a.cases]
    tag = time.strftime("%Y%m%d-%H%M%S") + "_" + pipe.model_name.replace("/", "_") + ("_" + src.name if a.src else "")
    run = ROOT / "runs" / tag
    inp, gt = run / "input", run / "gt"
    for c in cases:
        (inp / c).mkdir(parents=True, exist_ok=True)
        for f in (src / c).glob("*.pdf"):
            shutil.copy(f, inp / c / f.name)
    build_gt(train, pipe.specs, gt, cases)
    t0 = time.time()
    summary = pipe.run_dir(inp, run / "output", run / "trace", workers=a.workers, exclude_self=True)
    r = score_dirs(run / "output", gt, verbose=a.verbose)
    from o2j.llm import COST
    r["model"], r["cases"], r["elapsed_s"] = pipe.model_name, len(cases), round(time.time() - t0, 1)
    r["cost"] = dict(COST)
    r["misclassified"] = [x for x in summary if x["doctype"] not in Path(x["file"]).stem and
                          not (x["doctype"] == "przelew" and "przelew" in x["file"])]
    (run / "report.json").write_text(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"\nMODEL {r['model']}  cases={len(cases)}  F1={r['f1']:.4f}  {r['counts']}  time={r['elapsed_s']}s"
          f"  cost=${COST['usd']:.3f} ({COST['calls']} calls)")
    print("per doc:", r["per_doc"])
    for k, v in sorted(r["per_field"].items(), key=lambda x: x[1]["f1"])[:15]:
        print(f"  {v['f1']:.3f}  {k}  " + " ".join(f"{x}={v[x]}" for x in ("TP", "FP", "FN", "TN") if x in v))
    print("report:", run / "report.json")


if __name__ == "__main__":
    main()
