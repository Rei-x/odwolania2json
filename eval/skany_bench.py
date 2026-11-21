"""In-process variant of run_skany.py that also reports $ cost (OCR + extraction) and accepts settings overrides.

    python eval/skany_bench.py --src data/skany_uzp --ocr-model qwen/qwen3-vl-8b-instruct \
        [--model deepseek/deepseek-v4.1-flash] [--set 'llm.extra_body={provider: {only: [nebius]}}'] [--ocr-provider '{only: [nebius]}']
"""
from __future__ import annotations

import argparse
import shutil
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "data/skany_uzp")
    ap.add_argument("--model", default=None)
    ap.add_argument("--ocr-model", default=None)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--workers", type=int, default=8)
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
    pipe.run_dir(run / "input", run / "output", run / "trace", workers=a.workers)
    r = score_dirs(run / "output", run / "gt", verbose=False)
    n = sum(1 for _ in a.src.rglob("*.pdf"))
    print(f"\nSKANY ocr={a.ocr_model} llm={pipe.llm.model} docs={n} F1={r['f1']:.4f} {r['counts']} "
          f"time={time.time() - t0:.0f}s cost=${COST['usd']:.4f} ({COST['calls']} calls)")
    print("run:", run)


if __name__ == "__main__":
    main()
