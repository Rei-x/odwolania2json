"""OCR benchmark: CER of OCR engines on synthetic scans vs the original PDF text layer.

  python -m eval.ocr_bench --engine vlm --model moonshotai/kimi-k3.1-pro [--reasoning off]
  python -m eval.ocr_bench --engine paddle
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdfium2 as pdfium
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def ref_text(pdf: Path) -> str:
    d = pdfium.PdfDocument(str(pdf))
    t = d[0].get_textpage().get_text_range()
    return norm(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="vlm")
    ap.add_argument("--model", default=None)
    ap.add_argument("--reasoning", default=None, help="off -> disable reasoning (OpenRouter)")
    ap.add_argument("--scans", type=Path, default=ROOT / "data/scans")
    a = ap.parse_args()

    from o2j import ocr as O
    from o2j.config import load_settings
    s = load_settings()
    cfg = dict(s.get("ocr", {}))
    cfg["engine"] = a.engine
    if a.model:
        cfg["model"] = a.model
    if a.reasoning:
        cfg["reasoning"] = a.reasoning
    engine = O.make_engine(cfg, s["llm"])
    files = sorted(a.scans.rglob("*.pdf"))

    def one(f: Path):
        d = pdfium.PdfDocument(str(f))
        from o2j.pdf import render_png
        png = render_png(d[0], int(cfg.get("dpi", 200)))
        t0 = time.time()
        hyp = norm(engine(png))
        ref = ref_text(ROOT / "data/train" / f.parent.name / f.name)
        cer = Levenshtein.distance(hyp, ref) / max(1, len(ref))
        from collections import Counter
        h, r = Counter(hyp.split()), Counter(ref.split())
        inter = sum((h & r).values())
        wf1 = 2 * inter / max(1, sum(h.values()) + sum(r.values()))
        return {"file": f"{f.parent.name}/{f.name}", "cer": round(cer, 4), "word_err": round(1 - wf1, 4), "len_ref": len(ref),
                "len_hyp": len(hyp), "s": round(time.time() - t0, 1)}

    workers = 1 if a.engine == "paddle" else 8
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, files))
    for r in res:
        print(r)
    mean = sum(r["cer"] for r in res) / len(res)
    print(json.dumps({"engine": a.engine, "model": cfg.get("model"), "reasoning": cfg.get("reasoning"),
                      "mean_cer": round(mean, 4), "mean_word_err (bez kolejności)": round(sum(r["word_err"] for r in res) / len(res), 4), "max_cer": max(r["cer"] for r in res),
                      "mean_s": round(sum(r["s"] for r in res) / len(res), 1)}))


if __name__ == "__main__":
    main()
