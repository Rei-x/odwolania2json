"""List FP/FN of an eval run with a hint whether the GT value is present in the page text (OCR) or not.

    python eval/hard_errors.py runs/<run> [runs/<run2> ...]
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.score import compare  # noqa: E402


def _n(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return re.sub(r"[\s\-./,:;()\"'„”]", "", s)


def main():
    for run in map(Path, sys.argv[1:]):
        print(f"##### {run.name}")
        for gt_file in sorted((run / "gt").rglob("*.json")):
            rel = gt_file.relative_to(run / "gt")
            pf = run / "output" / rel
            tf = run / "trace" / rel.with_suffix(".trace.json")
            pred = json.loads(pf.read_text()) if pf.exists() else {}
            tr = json.loads(tf.read_text()) if tf.exists() else {}
            res = []
            compare(pred, json.loads(gt_file.read_text()), "", res)
            errs = [r for r in res if r[0] in ("FP", "FN")]
            if not errs and tr.get("doctype") in rel.stem:
                continue
            txt = _n(" ".join(p["text"] for p in tr.get("page_texts", [])))
            ocr_chars = [len(p["text"]) for p in tr.get("page_texts", [])]
            print(f"--- {rel}  doctype={tr.get('doctype')} ocr_pages={tr.get('ocr_pages')} chars={ocr_chars} "
                  f"err={tr.get('error', '')}")
            for kind, path, p, g in errs:
                where = ""
                if g not in (None, "", [], {}):
                    where = "GT_IN_TEXT" if _n(g) and _n(g) in txt else "GT_NOT_IN_TEXT"
                print(f"  {kind} {path}: pred={p!r} gt={g!r} [{where}]")


if __name__ == "__main__":
    main()
