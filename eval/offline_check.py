"""LLM-free diagnostics on data/variants (usable when the API budget is exhausted).

For every variant document:
  - rule-based classification scores (keywords + filename) and same with a neutral filename
  - feed the *ground truth* as if it were a perfect extraction through postprocess -> ground -> verify
    and list the issues verify() would raise. Any issue here means the repair loop gets asked to
    "fix" a correct value (typical: names in nominative not found literally in dative/accusative text).

Usage: python -m eval.offline_check
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.score import compare  # noqa: E402
from o2j import extract as E  # noqa: E402
from o2j import pdf as P  # noqa: E402
from o2j import verify as V  # noqa: E402
from o2j.classify import rule_scores  # noqa: E402
from o2j.config import load_settings  # noqa: E402
from o2j.spec import load_specs  # noqa: E402

DOCS = {"odwolanie": ("odwolanie.pdf", "odwolanie.json"), "pelnomocnictwo": ("pelnomocnictwo.pdf", "pelnomocnictwo.json"),
        "przelew": ("potwierdzenie_przelewu.pdf", "przelew.json")}


def main():
    s = load_settings()
    specs = load_specs(s["paths"]["doctypes"])
    for v in sorted((ROOT / "data" / "variants").iterdir()):
        if not v.is_dir():
            continue
        for dt, (pdf, js) in DOCS.items():
            if not (v / pdf).exists():
                continue
            doc = P.load(v / pdf)
            text = doc.text()
            sc = rule_scores(text[:6000], pdf, specs)
            sc_anon = rule_scores(text[:6000], "doc.pdf", specs)
            best = max(sc_anon, key=sc_anon.get)
            gt = json.loads((v / js).read_text())
            pp = E.postprocess(specs[dt], json.loads(json.dumps(gt)))
            diff = []
            compare(pp, gt, "", diff)
            pp_errs = [(k, p, a, b) for k, p, a, b in diff if k in ("FP", "FN")]
            ev = E.ground(doc, pp, E.derived_fields(specs[dt]))
            issues = V.verify(specs[dt], pp, ev)
            flag = "" if best == dt else f"  !! anon-filename rule class={best}"
            print(f"{v.name}/{dt}: rules={ {k: int(x) for k, x in sc_anon.items()} }{flag}")
            for e in pp_errs:
                print(f"    POSTPROCESS changes GT: {e}")
            for i in issues:
                print(f"    VERIFY flags correct value: {i['field']}={i['value']!r}")


if __name__ == "__main__":
    main()
