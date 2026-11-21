"""Adjudicate disagreements between our pipeline and the Opus reference (EVALUATION ONLY).

For every document with differing fields, Claude Opus 5.5 sees the PDF, the organiser's schema and, per field,
the two candidate values (anonymised as A/B in random order) and decides which is correct per the schema.

  python -m eval.adjudicate                       # uses runs/kio_ref/{pred,gt}
Writes runs/kio_adjudication.jsonl and prints adjusted error stats per field.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.opus_reference import KIO, system_for, trimmed_pdf  # noqa: E402
from eval.score import compare  # noqa: E402

load_dotenv(ROOT / ".env")
REF = ROOT / "runs/kio_ref"
OUT = ROOT / "runs/kio_adjudication.jsonl"

PROMPT = """Poniżej sporne pola z ekstrakcji tego dokumentu. Dla każdego pola są dwie kandydackie wartości A i B
(null = brak wartości). Oceń wyłącznie na podstawie dokumentu i zasad wzorca, która wartość jest poprawna.
Werdykty: "A", "B", "obie" (obie poprawne / równoważne wg zasad), "zadna" (obie błędne — podaj poprawną).

{items}

Zwróć JSON: {{"werdykty": [{{"pole": "...", "werdykt": "A|B|obie|zadna", "poprawna": <wartość lub null>, "uzasadnienie": "krótko"}}]}}"""

SCHEMA = {"type": "object", "properties": {"werdykty": {"type": "array", "items": {"type": "object", "properties": {
    "pole": {"type": "string"}, "werdykt": {"type": "string", "enum": ["A", "B", "obie", "zadna"]},
    "poprawna": {"type": ["string", "number", "null"]}, "uzasadnienie": {"type": "string"}},
    "required": ["pole", "werdykt", "poprawna", "uzasadnienie"], "additionalProperties": False}}},
    "required": ["werdykty"], "additionalProperties": False}


def disputes() -> dict:
    out = {}
    for gt in sorted((REF / "gt").rglob("*.json")):
        rel = gt.relative_to(REF / "gt")
        pp = REF / "pred" / rel
        pred = json.loads(pp.read_text()) if pp.exists() else {}
        res = []
        compare(pred, json.loads(gt.read_text()), "", res)
        bad = [(path, p, g, kind) for kind, path, p, g in res if kind in ("FP", "FN")]
        if bad:
            out[str(rel)] = bad
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    ds = disputes()
    done = {json.loads(l)["doc"] for l in open(OUT)} if OUT.exists() else set()
    jobs = [(k, v) for k, v in ds.items() if k not in done][: a.limit or None]
    client = anthropic.Anthropic()
    rng = random.Random(11)

    def one(job):
        rel, bad = job
        doctype = rel.split("/")[0]
        pdf = KIO / "pobrane" / (Path(rel).stem + ".pdf")
        data, _ = trimmed_pdf(pdf, 6)
        order, lines = [], []
        for i, (path, p, g, kind) in enumerate(bad):
            swap = rng.random() < 0.5  # hide which value is ours
            A, B = (g, p) if swap else (p, g)
            order.append(swap)
            lines.append(f"{i + 1}. pole `{path}`: A = {json.dumps(A, ensure_ascii=False)} | B = {json.dumps(B, ensure_ascii=False)}")
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=8000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=[{"type": "text", "text": system_for(doctype), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(data).decode()}},
                {"type": "text", "text": PROMPT.format(items="\n".join(lines))}]}])
        if resp.stop_reason == "refusal":
            return None
        verdicts = json.loads(next(b.text for b in resp.content if b.type == "text"))["werdykty"]
        recs = []
        for i, (path, p, g, kind) in enumerate(bad):
            v = verdicts[i] if i < len(verdicts) else {"werdykt": "?", "poprawna": None, "uzasadnienie": ""}
            w = v["werdykt"]
            if w in ("A", "B"):
                ours_is_a = not order[i]
                winner = "ours" if (w == "A") == ours_is_a else "opus"
            else:
                winner = {"obie": "both", "zadna": "neither"}.get(w, "?")
            recs.append({"path": path, "ours": p, "opus": g, "winner": winner, "correct": v.get("poprawna"),
                         "why": v.get("uzasadnienie", "")})
        return {"doc": rel, "fields": recs}

    with ThreadPoolExecutor(a.workers) as ex, open(OUT, "a") as fo:
        for r in ex.map(one, jobs):
            if r:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                fo.flush()
    rows = [json.loads(l) for l in open(OUT)]
    w = Counter(f["winner"] for r in rows for f in r["fields"])
    print("winners:", dict(w))
    per = Counter((r["doc"].split("/")[0], re.sub(r"\[\d+\]", "[]", f["path"])) for r in rows for f in r["fields"]
                  if f["winner"] in ("opus", "neither"))
    print("genuine pipeline errors per field:")
    for k, v in per.most_common(20):
        print(f"  {v:3d}  {k}")


if __name__ == "__main__":
    main()
