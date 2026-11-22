"""In-process variant of run_skany.py that also reports $ cost (OCR + extraction) and accepts settings overrides.

    python eval/skany_bench.py --src data/skany_uzp --ocr-model qwen/qwen3-vl-8b-instruct \
        [--model deepseek/deepseek-v4.1-flash] [--set 'llm.extra_body={provider: {only: [nebius]}}'] [--ocr-provider '{only: [nebius]}']
        [--ocr-cache runs/ocr_cache_skany.json]

--ocr-cache: page OCR text keyed by sha256 of the rendered page PNG (+ OCR model); pages found there are not sent
to the OCR model again, new pages are added. Lets A/B runs of the extraction step share identical OCR input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import threading
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from o2j import config as C  # noqa: E402
from o2j.llm import COST  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402
from eval.score import score_dirs  # noqa: E402


class CachedOCR:
    """Wraps an OCR engine (callable png -> text) with a JSON file cache (eval only)."""

    def __init__(self, engine, path: Path):
        self.engine, self.path, self.lock = engine, path, threading.Lock()
        self.model = getattr(engine, "model", None)
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.hits = self.misses = 0

    def __call__(self, png: bytes) -> str:
        key = f"{self.model}:{hashlib.sha256(png).hexdigest()}"
        with self.lock:
            if key in self.data:
                self.hits += 1
                return self.data[key]
        text = self.engine(png)
        with self.lock:
            self.misses += 1
            if (text or "").strip():  # never cache a failed page
                self.data[key] = text
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "data/skany_uzp")
    ap.add_argument("--model", default=None)
    ap.add_argument("--ocr-model", default=None)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ocr-cache", type=Path, default=None, help="JSON cache of page OCR text (see module docstring)")
    ap.add_argument("--ocr-provider", default=None,
                    help="YAML dict merged into OCR extra_body as `provider` (o2j/ocr.py has no extra_body setting yet)")
    a = ap.parse_args()
    if a.ocr_provider:
        import o2j.ocr as O
        prov, orig = yaml.safe_load(a.ocr_provider), O.openrouter_extra
        O.openrouter_extra = lambda base, extra: {**(orig(base, extra) or {}), "provider": prov}

    s = C.load_settings()
    if a.ocr_model:
        s.setdefault("ocr", {})["model"] = a.ocr_model
    for kv in a.set:
        k, v = kv.split("=", 1)
        d = s
        *head, last = k.split(".")
        for h in head:
            d = d.setdefault(h, {})
        d[last] = yaml.safe_load(v)

    tag = (a.ocr_model or "default").replace("/", "_")
    run = ROOT / "runs" / f"skany_bench_{time.strftime('%Y%m%d-%H%M%S')}_{tag}"
    for pdf in sorted(a.src.rglob("*.pdf")):
        case = f"{pdf.parent.parent.name}_{pdf.parent.name}"
        for kind, src in (("input", pdf), ("gt", pdf.with_suffix(".json"))):
            dst = run / kind / case / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)

    t0 = time.time()
    pipe = Pipeline(s, model=a.model)
    if a.ocr_cache and pipe._ocr is not None:
        pipe._ocr = CachedOCR(pipe._ocr, a.ocr_cache)
    pipe.run_dir(run / "input", run / "output", run / "trace", workers=a.workers)
    r = score_dirs(run / "output", run / "gt", verbose=False)
    n = sum(1 for _ in a.src.rglob("*.pdf"))
    print(f"\nSKANY ocr={a.ocr_model} llm={pipe.llm.model} docs={n} F1={r['f1']:.4f} {r['counts']} "
          f"time={time.time() - t0:.0f}s cost=${COST['usd']:.4f} ({COST['calls']} calls)")
    if isinstance(pipe._ocr, CachedOCR):
        print(f"OCR cache: {pipe._ocr.hits} pages reused, {pipe._ocr.misses} sent to the model ({a.ocr_cache})")
    print("run:", run)


if __name__ == "__main__":
    main()
