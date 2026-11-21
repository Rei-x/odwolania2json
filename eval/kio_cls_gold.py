"""Gold document-type labels for a slice of the KIO corpus, adjudicated by Claude Opus 5.5 (EVALUATION ONLY).

Slice = every document where our classifier disagreed with the corpus' rule labels + a random control sample
of agreements. Opus sees the first pages of the PDF and the organiser's type definitions.

  python -m eval.kio_cls_gold label      # -> runs/kio_cls_gold.jsonl
  python -m eval.kio_cls_gold score      # re-classify the slice with our pipeline and score against gold
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.opus_reference import trimmed_pdf  # noqa: E402

load_dotenv(ROOT / ".env")
KIO = ROOT / "data/kio_raw/pdf"
GOLD = ROOT / "runs/kio_cls_gold.jsonl"
TYPES = ["odwolanie", "pelnomocnictwo", "przelew", "inny"]

SYSTEM = """Klasyfikujesz dokumenty ze spraw odwoławczych w zamówieniach publicznych (Krajowa Izba Odwoławcza).
Typy:
- odwolanie: samo odwołanie wykonawcy wniesione do Prezesa KIO (pismo z zarzutami i żądaniami wobec czynności/zaniechań zamawiającego).
  NIE: informacja/zawiadomienie o wniesieniu odwołania, odpowiedź na odwołanie, cofnięcie/wycofanie odwołania, przystąpienie, wyrok, e-mail.
- pelnomocnictwo: dokument udzielający pełnomocnictwa (mocodawca ustanawia pełnomocnika). NIE: gwarancja, KRS, oświadczenie, e-mail.
- przelew: potwierdzenie wykonania przelewu bankowego (także wydruk z bankowości, także po angielsku). NIE: faktura, ogłoszenie, wezwanie.
- inny: wszystko pozostałe (ogłoszenia TED/BZP, SWZ, wyroki, korespondencja, gwarancje, puste/nieczytelne strony itd.).
Oceniaj treść dokumentu, nie nazwę pliku."""


def cmd_label(a):
    rows = [json.loads(l) for l in open(ROOT / "runs/kio_classify.jsonl")]
    dis = [r for r in rows if (r["label"] or "inny") != r["pred"]]
    agree = [r for r in rows if (r["label"] or "inny") == r["pred"]]
    random.Random(3).shuffle(agree)
    sl = dis + agree[: a.control]
    done = {json.loads(l)["file"] for l in open(GOLD)} if GOLD.exists() else set()
    client = anthropic.Anthropic()
    schema = {"type": "object", "properties": {"typ": {"type": "string", "enum": TYPES},
                                               "uzasadnienie": {"type": "string"}},
              "required": ["typ", "uzasadnienie"], "additionalProperties": False}

    def one(r):
        if r["file"] in done:
            return None
        data, total = trimmed_pdf(KIO / "pobrane" / r["file"], 3)
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(data).decode()}},
                {"type": "text", "text": "Jaki to typ dokumentu?"}]}])
        if resp.stop_reason == "refusal":
            return {**r, "gold": None, "why": "refusal"}
        out = json.loads(next(b.text for b in resp.content if b.type == "text"))
        return {"file": r["file"], "label": r["label"], "pred_v1": r["pred"], "source_label": r["source_label"],
                "gold": out["typ"], "why": out["uzasadnienie"], "slice": "disagree" if r in dis else "control"}

    with ThreadPoolExecutor(8) as ex, open(GOLD, "a") as fo:
        for res in ex.map(one, sl):
            if res:
                fo.write(json.dumps(res, ensure_ascii=False) + "\n")
                fo.flush()
    print(f"gold labels: {sum(1 for _ in open(GOLD))}")


def cmd_score(a):
    from collections import Counter

    from o2j import pdf as P
    from o2j.classify import classify
    from o2j.llm import COST
    from o2j.pipeline import Pipeline
    pipe = Pipeline()
    gold = [json.loads(l) for l in open(GOLD) if json.loads(l).get("gold")]

    def one(g):
        f = KIO / "pobrane" / g["file"]
        doc = P.load(f, ocr=pipe._ocr, ocr_max_pages=1, prep=pipe.s["ocr"].get("preprocess"),
                     min_chars=int(pipe.s["ocr"].get("min_chars_per_page", 40)))
        typ, _ = classify(doc.text(), Path("dokument.pdf"), pipe.specs, pipe.llm, 3, "llm_confirm")
        return g, typ

    res = list(ThreadPoolExecutor(16).map(one, gold))
    ok = sum(t == g["gold"] for g, t in res)
    print(f"accuracy vs Opus gold: {ok}/{len(res)} = {ok/len(res):.3f}   cost=${COST['usd']:.3f}")
    print("errors (gold -> ours):", Counter((g["gold"], t) for g, t in res if t != g["gold"]).most_common())
    if a.verbose:
        for g, t in res:
            if t != g["gold"]:
                print(f"  {g['gold']:14s} -> {t:14s} | {(g['source_label'] or '')[:50]} | {g['why'][:110]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["label", "score"])
    ap.add_argument("--control", type=int, default=30)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args()
    {"label": cmd_label, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
