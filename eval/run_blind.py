"""Final evaluation on the frozen BLIND test set (data/blind/blind_NN).

Runs the pipeline on every PDF, scores with eval.score and prints ONLY aggregate numbers:
overall F1, per-doctype F1 and LLM cost. Per-field errors are hidden unless --details is given
(they are always written to <out>/errors.tsv only with --details, so nothing leaks by default).

Blind cases are not in data/train, so no few-shot exclusion is needed.

Usage: python -m eval.run_blind [--workers 8] [--model M] [--out runs/blind_<ts>] [--details]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BLIND = ROOT / "data" / "blind"
GT_NAME = {"odwolanie.json": "odwolanie.json", "pelnomocnictwo.json": "pelnomocnictwo.json",
           "przelew.json": "potwierdzenie_przelewu.json"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / ("blind_" + time.strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default=None)
    ap.add_argument("--details", action="store_true", help="also print/write per-field errors (breaks blindness)")
    a = ap.parse_args(argv)

    from eval.score import compare, score_dirs
    from o2j import extract as E
    from o2j.llm import COST
    from o2j.pipeline import Pipeline

    cases = sorted(p for p in BLIND.iterdir() if p.is_dir() and p.name.startswith("blind_"))
    inp, gt, out = a.out / "input", a.out / "gt", a.out / "output"
    jobs = []
    for c in cases:
        for js in c.glob("*.json"):  # case GT (renamed to the PDF stem) or {} for out-of-scope documents
            (gt / c.name).mkdir(parents=True, exist_ok=True)
            shutil.copy(js, gt / c.name / GT_NAME.get(js.name, js.name))
        for pdf in sorted(c.glob("*.pdf")):
            (inp / c.name).mkdir(parents=True, exist_ok=True)
            shutil.copy(pdf, inp / c.name / pdf.name)
            jobs.append(inp / c.name / pdf.name)

    pipe = Pipeline(model=a.model)

    def job(p):
        rel = p.relative_to(inp).with_suffix(".json")
        try:
            _, result, _ = pipe.process(p)
        except Exception as e:  # noqa: BLE001
            result = {}
            print(f"  error on a document: {type(e).__name__}", flush=True)
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(E.dumps(result), encoding="utf-8")

    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, _ in enumerate(ex.map(job, jobs), 1):
            print(f"\r[{i}/{len(jobs)}] documents processed", end="", flush=True)
    print()

    r = score_dirs(out, gt)
    negs = [g for g in gt.rglob("*.json") if json.loads(g.read_text()) == {}]
    neg_ok = sum(1 for g in negs if (out / g.relative_to(gt)).exists()
                 and not json.loads((out / g.relative_to(gt)).read_text()))
    summary = {"f1": round(r["f1"], 4), "per_doc": r["per_doc"], "cases": len(cases), "documents": len(jobs),
               "cost_usd": round(COST["usd"], 4), "llm_calls": COST["calls"], "elapsed_s": round(time.time() - t0, 1),
               "model": pipe.llm.model, "negatives_rejected": f"{neg_ok}/{len(negs)}"}
    (a.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nBLIND F1 = {summary['f1']:.4f}   ({len(cases)} cases, {len(jobs)} documents)")
    print("per doctype F1:", {k: f"{v:.4f}" for k, v in sorted(r["per_doc"].items()) if k in ("odwolanie", "pelnomocnictwo", "potwierdzenie_przelewu")})
    print(f"out-of-scope documents correctly returned {{}}: {neg_ok}/{len(negs)}  (wrong extractions count as FP in F1)")
    print(f"cost = ${COST['usd']:.3f} ({COST['calls']} LLM calls), time = {summary['elapsed_s']}s, model = {summary['model']}")

    if a.details:
        errs = []
        for g in sorted(gt.rglob("*.json")):
            rel = g.relative_to(gt)
            pf = out / rel
            res = []
            compare(json.loads(pf.read_text()) if pf.exists() else {}, json.loads(g.read_text()), "", res)
            errs += ["\t".join([str(rel), k, path, json.dumps(p, ensure_ascii=False), json.dumps(v, ensure_ascii=False)])
                     for k, path, p, v in res if k in ("FP", "FN")]
        (a.out / "errors.tsv").write_text("\n".join(errs), encoding="utf-8")
        print("\nerrors:\n  " + "\n  ".join(errs))
    else:
        # remove anything that would reveal case content in the run dir
        shutil.rmtree(gt, ignore_errors=True)
        shutil.rmtree(inp, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)
    print("summary:", a.out / "summary.json")


if __name__ == "__main__":
    main()
