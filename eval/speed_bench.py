"""Per-document speed benchmark: documents processed ONE AT A TIME (no concurrency between documents),
wall time + per-step durations from trace["steps"], LLM cost, and F1 against the reference JSON.

Default set: the hard scans shown in the GUI (samples/), mapped to their reference JSON. Scans derived from
a training case exclude that case from few-shot retrieval (no leakage).

    python -m eval.speed_bench [--profile auto] [--skany N] [--out runs/speed_<ts>.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# sample -> (reference JSON relative to data/, training case to exclude from few-shot)
SAMPLES = {
    "skan-uzp-odwolanie.pdf": ("skany_uzp/odwolania/0001/0001.json", None),
    "skan-obrocony-90-odwolanie.pdf": ("train/przyklad_14/odwolanie.json", "przyklad_14"),
    "skan-silny-szum-przelew.pdf": ("train/przyklad_26/przelew.json", "przyklad_26"),
    "zdjecie-telefonem-pelnomocnictwo.pdf": ("train/przyklad_50/pelnomocnictwo.json", "przyklad_50"),
    "pieczec-na-tekscie-pelnomocnictwo.pdf": ("train/przyklad_38/pelnomocnictwo.json", "przyklad_38"),
}


def _data_root() -> Path:
    # data/ is partly untracked; in a git worktree fall back to the main checkout's copy
    d = ROOT / "data"
    if (d / "skany_uzp").exists():
        return d
    alt = ROOT.parent / "odwolania2json" / "data"
    return alt if alt.exists() else d


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--skany", type=int, default=0, help="also process the first N organiser scans (data/skany_uzp)")
    ap.add_argument("--no-samples", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / ("speed_" + time.strftime("%Y%m%d-%H%M%S") + ".json"))
    a = ap.parse_args(argv)

    from eval.score import compare, f1
    from o2j import config as C
    from o2j.llm import COST
    from o2j.pipeline import Pipeline

    data = _data_root()
    items = [] if a.no_samples else [(ROOT / "samples" / n, data / g, ex) for n, (g, ex) in SAMPLES.items()]
    if a.skany:
        items += [(p, p.with_suffix(".json"), None) for p in sorted((data / "skany_uzp").rglob("*.pdf"))[: a.skany]]

    pipe = Pipeline(C.load_settings(profile=a.profile))
    rows, tot = [], {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    for pdf, gt, ex in items:
        c0, t0 = COST["usd"], time.time()
        try:
            doctype, result, trace = pipe.process(pdf, {ex} if ex else set())
            err = None
        except Exception as e:  # noqa: BLE001
            doctype, result, trace, err = "ERROR", {}, {}, repr(e)
        dt = time.time() - t0
        res: list = []
        compare(result, json.loads(gt.read_text(encoding="utf-8")), "", res)
        cnt = {k: sum(1 for r in res if r[0] == k) for k in tot}
        for k in tot:
            tot[k] += cnt[k]
        steps = {s["id"]: round(s.get("duration_s") or 0, 1) for s in trace.get("steps", [])}
        calls = {s["id"]: [s.get("calls"), (s.get("tokens") or {}).get("completion")]
                 for s in trace.get("steps", []) if s.get("calls")}
        ocr = [[p["ocr"].get("duration_s"), (p["ocr"].get("tokens") or {}).get("completion")]
               for s in trace.get("steps", []) if s["id"] == "load" for p in s["detail"].get("pages", []) if p.get("ocr")]
        row = {"file": pdf.name, "doctype": doctype, "seconds": round(dt, 1), "f1": round(f1(cnt), 4),
               "cost_usd": round(COST["usd"] - c0, 5), "steps": steps, "calls_tokens": calls, "ocr_pages": ocr, "error": err,
               "classification": (trace.get("classification") or {}).get("method"),
               "router": (trace.get("router") or {}).get("reasons")}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    summary = {"profile": pipe.s.get("active_profile"), "docs": len(rows),
               "total_seconds": round(sum(r["seconds"] for r in rows), 1),
               "mean_seconds": round(sum(r["seconds"] for r in rows) / max(1, len(rows)), 1),
               "f1": round(f1(tot), 4), "counts": tot, "cost_usd": round(COST["usd"], 4)}
    print("SUMMARY", json.dumps(summary))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
