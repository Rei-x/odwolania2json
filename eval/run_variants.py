"""Run the pipeline on data/variants and score against variant GT.

Few-shot leakage guard: each variant is derived from data/train/<case>, so that source case is
excluded from few-shot retrieval (the plain `run.py --input` path would happily retrieve it).

Usage: python -m eval.run_variants [--out runs/variants_<ts>] [--only VARIANT ...] [--workers 8]
Writes <out>/{input,gt,output,trace}/<variant>/..., report.json, errors.tsv
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.score import compare, f1, score_dirs  # noqa: E402
from o2j import extract as E  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

VAR = ROOT / "data" / "variants"
GT_NAME = {"odwolanie.json": "odwolanie.json", "pelnomocnictwo.json": "pelnomocnictwo.json",
           "przelew.json": "potwierdzenie_przelewu.json"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / ("variants_" + time.strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default=None)
    ap.add_argument("--mode", default=None, help="override extraction.mode (llm | deterministic)")
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args(argv)
    vs = sorted(p for p in VAR.iterdir() if p.is_dir() and (not a.only or p.name in a.only))
    inp, gt, out, tr = (a.out / x for x in ("input", "gt", "output", "trace"))
    jobs = []
    for v in vs:
        src_case = "_".join(v.name.split("_")[:2])  # przyklad_NN
        for js, gname in GT_NAME.items():
            if (v / js).exists():
                (gt / v.name).mkdir(parents=True, exist_ok=True)
                shutil.copy(v / js, gt / v.name / gname)
        for pdf in v.glob("*.pdf"):
            (inp / v.name).mkdir(parents=True, exist_ok=True)
            shutil.copy(pdf, inp / v.name / pdf.name)
            jobs.append((inp / v.name / pdf.name, src_case))
    if not a.score_only:
        pipe = Pipeline(model=a.model, mode=a.mode)

        def job(p, src_case):
            rel = p.relative_to(inp).with_suffix(".json")
            try:
                doctype, result, trace = pipe.process(p, {src_case})
            except Exception as e:  # noqa: BLE001
                doctype, result, trace = "error", {}, {"error": repr(e)}
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(E.dumps(result), encoding="utf-8")
            (tr / rel).parent.mkdir(parents=True, exist_ok=True)
            (tr / rel.with_suffix(".trace.json")).write_text(E.dumps(trace), encoding="utf-8")
            return str(rel), doctype

        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(job, p, c) for p, c in jobs]
            for i, f in enumerate(as_completed(futs), 1):
                rel, dt = f.result()
                print(f"[{i}/{len(jobs)}] {rel} -> {dt}", flush=True)

    r = score_dirs(out, gt)
    # per-variant F1 + error list
    per_var, errs = defaultdict(lambda: defaultdict(int)), []
    for g in sorted(gt.rglob("*.json")):
        rel = g.relative_to(gt)
        pf = out / rel
        res = []
        compare(json.loads(pf.read_text()) if pf.exists() else {}, json.loads(g.read_text()), "", res)
        for kind, path, p, gv in res:
            per_var[rel.parts[0]][kind] += 1
            if kind in ("FP", "FN"):
                errs.append((str(rel), kind, path, json.dumps(p, ensure_ascii=False), json.dumps(gv, ensure_ascii=False)))
    r["per_variant"] = {k: round(f1(v), 4) for k, v in per_var.items()}
    (a.out / "report.json").write_text(json.dumps(r, ensure_ascii=False, indent=2))
    (a.out / "errors.tsv").write_text("\n".join("\t".join(e) for e in errs), encoding="utf-8")
    print(f"\nF1 = {r['f1']:.4f}  {r['counts']}\nper doc: {r['per_doc']}")
    for k, v in sorted(r["per_variant"].items()):
        print(f"  {v:.4f}  {k}")
    print("\nerrors:")
    for e in errs:
        print("  " + "\t".join(e))
    print("out:", a.out)


if __name__ == "__main__":
    main()
