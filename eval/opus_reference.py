"""Reference labels for real (unlabelled) KIO documents with Claude Opus 5.5 — EVALUATION ONLY.

Claude is not open-source, so it is never part of the submitted pipeline. Here it plays an independent
annotator: it reads the PDF natively and fills the UZP schema using ONLY the organiser's schema files
(data/schemas/*.json with field comments + the reason-code dictionary) — none of our prompts or rules.

  python -m eval.opus_reference sample --per-type 15      # pick docs, write Opus references
  python -m eval.opus_reference compare                   # run our pipeline on them and score vs Opus
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import pypdfium2 as pdfium
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from o2j.spec import load_specs  # noqa: E402

load_dotenv(ROOT / ".env")
KIO = ROOT / "data/kio_raw/pdf"
OUT = ROOT / "runs/kio_ref"
MODEL = "claude-opus-5-5"
MAX_PAGES = 6  # key data sits on the first pages (also what our pipeline reads)
SCHEMA_FILE = {"odwolanie": "odwolanie.json", "pelnomocnictwo": "pelnomocnictwo.json", "przelew": "przelew.json"}
PRICE_IN, PRICE_OUT, PRICE_CACHE_READ, PRICE_CACHE_WRITE = 4e-6, 20e-6, 0.4e-6, 5e-6

SYSTEM = """Jesteś ekspertem od zamówień publicznych i starannym annotatorem danych.
Otrzymasz dokument PDF i masz wypełnić JSON dokładnie według poniższego wzorca organizatora.
Komentarze (//) we wzorcu opisują znaczenie i format pól — stosuj je ściśle.
Zasady: przepisuj wartości wiernie z dokumentu; czego nie ma w dokumencie — null (listy mogą być puste);
nie zgaduj. Daty YYYY-MM-DD. Imiona i nazwiska w mianowniku, bez tytułów zawodowych.

### Wzorzec ({doctype})
{template}
{extra}"""


def trimmed_pdf(path: Path, n: int = MAX_PAGES) -> tuple[bytes, int]:
    from o2j.pdf import _PDFIUM_LOCK  # pdfium is not thread-safe
    with _PDFIUM_LOCK:
        return _trimmed(path, n)


def _trimmed(path: Path, n: int) -> tuple[bytes, int]:
    src = pdfium.PdfDocument(str(path))
    total = len(src)
    if total <= n:
        return path.read_bytes(), total
    dst = pdfium.PdfDocument.new()
    dst.import_pages(src, list(range(n)))
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue(), total


def system_for(doctype: str) -> str:
    template = (ROOT / "data/schemas" / SCHEMA_FILE[doctype]).read_text(encoding="utf-8")
    extra = ""
    if doctype == "odwolanie":
        extra = "\n### Słownik czynnosc_powod_id\n" + (ROOT / "data/schemas/czynnosc_powod_id_dict.md").read_text(encoding="utf-8")
    return SYSTEM.format(doctype=doctype, template=template, extra=extra)


def _unions(schema) -> int:
    if isinstance(schema, dict):
        own = int("anyOf" in schema or isinstance(schema.get("type"), list))
        return own + sum(_unions(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(_unions(v) for v in schema)
    return 0


def annotate(client, specs, doctype: str, pdf: Path) -> dict:
    data, total = trimmed_pdf(pdf)
    schema = specs[doctype].json_schema()
    # Anthropic structured outputs allow <= 16 union-typed params; larger schemas -> JSON in text, parsed below
    fmt = {"format": {"type": "json_schema", "schema": schema}} if _unions(schema) <= 16 else {}
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", **fmt},
        system=[{"type": "text", "text": system_for(doctype), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": base64.standard_b64encode(data).decode()}},
            {"type": "text", "text": f"Wypełnij JSON dla tego dokumentu (typ: {doctype})."
                                     + ("" if fmt else " Zwróć wyłącznie obiekt JSON o strukturze wzorca, bez komentarzy i bez markdown.")
                                     + (f" Załączono pierwsze {MAX_PAGES} z {total} stron." if total > MAX_PAGES else "")},
        ]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"refusal: {getattr(resp, 'stop_details', None)}")
    text = "".join(b.text for b in resp.content if b.type == "text")
    if not fmt:
        from o2j.llm import parse_json
        from o2j.extract import postprocess
        parsed = postprocess(specs[doctype], parse_json(text))  # only reshapes to schema + normalises formats
        text = json.dumps(parsed, ensure_ascii=False)
    u = resp.usage
    cost = ((u.input_tokens or 0) * PRICE_IN + (u.output_tokens or 0) * PRICE_OUT
            + (u.cache_read_input_tokens or 0) * PRICE_CACHE_READ + (u.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE)
    return {"result": json.loads(text), "cost": cost, "pages": total, "request_id": resp._request_id}


def cmd_sample(a):
    rows = [json.loads(l) for l in open(ROOT / "runs/kio_classify.jsonl")]
    rng = random.Random(a.seed)
    specs = load_specs(ROOT / "config/doctypes")
    client = anthropic.Anthropic()
    jobs = []
    if a.all:
        # whole corpus: type from Opus gold label when adjudicated, else our classifier; scans included
        gold = {}
        gp = ROOT / "runs/kio_cls_gold.jsonl"
        if gp.exists():
            gold = {g["file"]: g["gold"] for g in map(json.loads, open(gp)) if g.get("gold")}
        for r in rows:
            t = gold.get(r["file"], r["pred"])
            if t in SCHEMA_FILE:
                jobs.append((t, KIO / "pobrane" / r["file"]))
    for doctype in ([] if a.all else SCHEMA_FILE):
        # agreed type (corpus rules == our classifier), text layer; one doc per proceeding for diversity
        cand = [r for r in rows if r["label"] == doctype and r["pred"] == doctype and r["text_mode"] == "tekst"]
        rng.shuffle(cand)
        idx = {json.loads(l)["file"]: json.loads(l) for l in open(KIO / "indeks.jsonl")}
        seen, pick = set(), []
        for r in cand:
            src = idx[r["file"]].get("source")
            if src in seen:
                continue
            seen.add(src)
            pick.append(r)
            if len(pick) >= a.per_type:
                break
        jobs += [(doctype, KIO / "pobrane" / r["file"]) for r in pick]

    def one(job):
        doctype, pdf = job
        out = OUT / "gt" / doctype / (pdf.stem + ".json")
        if out.exists():
            return 0.0, "cached"
        try:
            r = annotate(client, specs, doctype, pdf)
        except Exception as e:  # noqa: BLE001
            return 0.0, f"ERROR {pdf.name}: {e!r}"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r["result"], ensure_ascii=False, indent=2), encoding="utf-8")
        inp = OUT / "input" / doctype / pdf.name
        inp.parent.mkdir(parents=True, exist_ok=True)
        inp.write_bytes(pdf.read_bytes())
        return r["cost"], f"ok {doctype} {pdf.name[:12]} pages={r['pages']} ${r['cost']:.3f}"

    total = 0.0
    with ThreadPoolExecutor(a.workers) as ex:
        for cost, msg in ex.map(one, jobs):
            total += cost
            print(msg, flush=True)
    print(f"Opus reference cost: ${total:.2f} for {len(jobs)} docs")


def cmd_compare(a):
    out_dir = OUT / "pred"
    subprocess.run([sys.executable, str(ROOT / "run.py"), "--input", str(OUT / "input"), "--output", str(out_dir),
                    "--trace", str(OUT / "trace"), "--workers", "8"], check=True)
    subprocess.run([sys.executable, "-m", "eval.score", str(out_dir), str(OUT / "gt")] + (["-v"] if a.verbose else []),
                   check=True, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "compare"])
    ap.add_argument("--per-type", type=int, default=15)
    ap.add_argument("--all", action="store_true", help="annotate every corpus document of the 3 types")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    {"sample": cmd_sample, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    main()
