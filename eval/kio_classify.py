"""Classify the public KIO corpus (data/kio_raw/pdf) and compare with the corpus' rule-based labels."""
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from o2j import pdf as P  # noqa: E402
from o2j.classify import classify  # noqa: E402
from o2j.llm import COST  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

BASE = ROOT / "data/kio_raw/pdf"
OUT = ROOT / "runs/kio_classify.jsonl"


def main():
    pipe = Pipeline()
    recs = [json.loads(l) for l in open(BASE / "indeks.jsonl")]
    done = {}
    if OUT.exists():
        for l in open(OUT):
            r = json.loads(l)
            done[r["file"]] = r

    def one(r):
        if r["file"] in done:
            return done[r["file"]]
        f = BASE / "pobrane" / r["file"]
        try:
            doc = P.load(f, ocr=pipe._ocr, ocr_max_pages=1, prep=pipe.s["ocr"].get("preprocess"))
            typ, info = classify(doc.text(), Path("dokument.pdf"), pipe.specs, pipe.llm, 3, "llm_confirm")
            err = None
        except Exception as e:  # noqa: BLE001
            typ, info, err = "error", {}, repr(e)
        return {"file": r["file"], "label": r.get("type"), "status": r.get("status"), "text_mode": r.get("text_mode"),
                "source_label": r.get("source_label"), "pred": typ, "method": info.get("method"), "error": err}

    with ThreadPoolExecutor(16) as ex, open(OUT, "a") as fo:
        for i, res in enumerate(ex.map(one, recs), 1):
            if res["file"] not in done:
                fo.write(json.dumps(res, ensure_ascii=False) + "\n")
                fo.flush()
            if i % 100 == 0:
                print(f"{i}/{len(recs)}  cost=${COST['usd']:.3f}", flush=True)
    rows = [json.loads(l) for l in open(OUT)]
    cm = Counter((r["label"] or "brak", r["pred"]) for r in rows)
    print("\nlabel(corpus) -> pred(ours):")
    for k, v in sorted(cm.items()):
        print(f"  {v:4d}  {k[0]:15s} -> {k[1]}")
    print(f"errors: {sum(1 for r in rows if r['error'])}  cost=${COST['usd']:.3f}")


if __name__ == "__main__":
    main()
