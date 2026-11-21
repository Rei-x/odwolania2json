"""How large must the rule margin be before the LLM classification vote can be skipped? (offline, no LLM)

For every labelled document (training references + negatives, blind set + blind negatives, optionally a
JSONL of extra labelled PDFs {"file": path, "gold": type} and OCR text from run traces) computes the keyword
rule scores and reports, per candidate margin, how many in-scope documents would skip the LLM and how many
skipped documents the rules alone would get wrong (that must stay 0).

    python -m eval.cls_margin [--extra labels.jsonl --extra-root DIR] [--traces 'runs/x/trace/*/*.trace.json']
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRUTH = {"odwolanie.pdf": "odwolanie", "pelnomocnictwo.pdf": "pelnomocnictwo",
         "potwierdzenie_przelewu.pdf": "przelew", "przelew.pdf": "przelew"}
TRACE_TYPE = {"odwolania": "odwolanie", "pelnomocnictwa": "pelnomocnictwo", "potwierdzenia": "przelew"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", type=Path, help="JSONL with {file, gold} of extra labelled PDFs")
    ap.add_argument("--extra-root", type=Path, default=Path("."))
    ap.add_argument("--traces", help="glob of *.trace.json (OCR text of scans; type from the case folder prefix)")
    ap.add_argument("--margins", default="5,6,7,8,9,10")
    a = ap.parse_args(argv)

    from o2j import pdf as P
    from o2j.classify import rule_scores
    from o2j.spec import load_specs
    specs = load_specs(ROOT / "config" / "doctypes")
    rows = []

    def add(src, name, text, truth):
        r = sorted(rule_scores(text[:6000], "", specs).items(), key=lambda x: -x[1])
        rows.append({"src": src, "name": name, "truth": truth, "best": r[0][0], "margin": r[0][1] - r[1][1]})

    for f in sorted((ROOT / "data/train").glob("*/*.pdf")):
        add("train", f.name, P.load(f).text(), TRUTH.get(f.name, "inny"))
    for f in sorted((ROOT / "data/blind").glob("*/*.pdf")):
        add("blind", f.name, P.load(f).text(), "inny" if "negatyw" in f.parent.name else TRUTH.get(f.name, "inny"))
    if a.extra:
        for line in a.extra.read_text().splitlines():
            g = json.loads(line)
            f = next(iter(a.extra_root.rglob(g["file"])), None)
            if f:
                add("extra", g["file"], P.load(f).text(), g["gold"])
    if a.traces:
        for tr in glob.glob(a.traces):
            d = json.loads(Path(tr).read_text())
            text = "\n\n".join(f"=== Strona {p['page']} ===\n{p['text']}" for p in d.get("page_texts", []))
            typ = TRACE_TYPE.get(Path(tr).parent.name.split("_")[0])
            if typ:
                add("scans_ocr", tr, text, typ)

    for m in (float(x) for x in a.margins.split(",")):
        parts = []
        for src in dict.fromkeys(r["src"] for r in rows):
            g = [r for r in rows if r["src"] == src]
            skip = [r for r in g if r["margin"] >= m]
            parts.append(f"{src}: skip {sum(r['truth'] != 'inny' for r in skip)}/{sum(r['truth'] != 'inny' for r in g)}"
                         f" wrong {sum(r['best'] != r['truth'] for r in skip)}")
        print(f"margin >= {m:g}  " + " | ".join(parts))
    worst = sorted((r for r in rows if r["best"] != r["truth"]), key=lambda r: -r["margin"])[:5]
    print("largest margins among documents the rules get wrong:",
          [(r["src"], r["truth"], r["best"], r["margin"]) for r in worst])


if __name__ == "__main__":
    main()
