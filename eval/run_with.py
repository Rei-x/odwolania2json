"""Run `run.py eval` with settings overrides and/or an image-preprocessing prototype, without touching o2j/.

    python eval/run_with.py --set ocr.dpi=300 --set ocr.max_tokens=20000 --pre flat,deskew,orient -- eval --src data/hard_scans/faded

--set key=value   dotted override of config/settings.yaml (value parsed as YAML)
--pre steps       comma list of preprocessing steps applied to every page rendered for OCR (affects both the OCR
                  input and the page images attached to the extraction call), see eval/preprocess.py
--tag suffix      appended to the --src name so the run dir is distinguishable
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import run  # noqa: E402
from o2j import config as C  # noqa: E402
from o2j import pdf as P  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--pre", default="")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    rest = [x for x in a.rest if x != "--"]

    base = C.load_settings()
    for kv in a.set:
        k, v = kv.split("=", 1)
        d = base
        *head, last = k.split(".")
        for h in head:
            d = d.setdefault(h, {})
        d[last] = yaml.safe_load(v)
    run.load_settings = lambda *x, **y: base

    if a.pre:
        from eval.preprocess import make_render
        P.render_png = make_render(a.pre.split(","), P.render_png)
    run.main(rest)


if __name__ == "__main__":
    main()
