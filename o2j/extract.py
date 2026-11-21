"""Spec-driven extraction: prompt building, few-shot retrieval, post-processing, grounding."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from . import normalize as N
from . import pdf as P
from .spec import DocSpec

SYSTEM = """Jesteś precyzyjnym systemem ekstrakcji danych z polskich dokumentów prawnych (zamówienia publiczne, Krajowa Izba Odwoławcza).
Zasady:
- Zwracasz WYŁĄCZNIE obiekt JSON o podanej strukturze (te same klucze, ta sama kolejność).
- Wartości przepisujesz z dokumentu wiernie, litera po literze (pisownia, wielkie litery, obecność lub brak polskich znaków) — nawet jeśli zapis wygląda na literówkę, NIE poprawiaj go; nie dopisujesz niczego, czego nie ma w dokumencie.
- Gdy informacji nie ma w dokumencie, wpisz null (listy mogą być puste). Nigdy nie zgaduj.
- Daty w formacie YYYY-MM-DD. Numery identyfikacyjne (KRS, NIP, REGON, rachunki) bez spacji i myślników.
- Listy zawierają tylko faktycznie występujące podmioty/osoby — nie dopełniaj ich.

Typ dokumentu: {name} — {description}

Pola do wyodrębnienia:
{guide}

Reguły szczegółowe dla tego typu dokumentu:
{instructions}"""


# ---------------------------------------------------------------- few-shot
@lru_cache(maxsize=512)
def _example_text(pdf_path: str, pages: int | None) -> str:
    return P.load(Path(pdf_path), max_pages=pages).text(pages)


def few_shot_examples(spec: DocSpec, train_dir: Path, query_text: str, exclude: set[str], k: int) -> list[tuple[str, str]]:
    ex = spec.raw.get("examples") or {}
    if not k or not ex or not train_dir or not train_dir.exists():
        return []
    cands = []
    for case in sorted(train_dir.iterdir()):
        pdf, js = case / ex["pdf"], case / ex["json"]
        if case.name in exclude or not pdf.exists() or not js.exists():
            continue
        cands.append((case.name, pdf, js))
    q = query_text[:3000]
    scored = []
    for name, pdf, js in cands:
        t = _example_text(str(pdf), spec.pages)
        scored.append((fuzz.ratio(q, t[:3000]), name, t, js))
    scored.sort(key=lambda x: -x[0])
    return [(t, js.read_text(encoding="utf-8")) for _, _, t, js in scored[:k]]


def build_prompt(spec: DocSpec, doc_text: str, examples: list[tuple[str, str]]) -> tuple[str, str]:
    system = SYSTEM.format(name=spec.name, description=spec.description, guide=spec.field_guide(),
                           instructions=spec.instructions.strip() or "-")
    parts = []
    for i, (t, js) in enumerate(examples, 1):
        parts.append(f"### PRZYKŁAD {i} — DOKUMENT\n{t}\n\n### PRZYKŁAD {i} — POPRAWNY WYNIK JSON\n{js.strip()}\n")
    parts.append(f"### DOKUMENT DO ANALIZY\n{doc_text}\n\n### Zwróć wynik JSON dla dokumentu do analizy.")
    return system, "\n".join(parts)


# ---------------------------------------------------------------- post-processing
def postprocess(spec: DocSpec, raw: dict) -> dict:
    return _pp_object(spec.fields, raw or {})


def _pp_object(props: dict, raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, node in props.items():
        out[k] = _pp(node, raw.get(k), raw)
    # derived fields (e.g. label of an enum sibling)
    for k, node in props.items():
        d = node.get("derive")
        if d and "label_of" in d:
            src = props[d["label_of"]]
            labels = {e["value"]: e["label"] for e in src["values"] if isinstance(e, dict)}
            out[k] = labels.get(out.get(d["label_of"]))
    return out


def _pp(node: dict, v, parent):
    t = node["type"]
    if t == "object":
        if v is None and node.get("nullable"):
            return None
        return _pp_object(node["properties"], v if isinstance(v, dict) else {})
    if t == "array":
        items = v if isinstance(v, list) else ([] if v is None else [v])
        res = [_pp(node["items"], it, None) for it in items]
        return [r for r in res if not _all_null(r)]
    if t == "enum":
        vals = [e["value"] if isinstance(e, dict) else e for e in node["values"]]
        if v in vals:
            return v
        for cand in vals:  # tolerate "4" vs 4, label instead of value
            if str(cand) == str(v).strip():
                return cand
            if isinstance(node["values"][vals.index(cand)], dict) and \
                    str(v).strip().lower() == node["values"][vals.index(cand)]["label"].lower():
                return cand
        return None
    return N.apply(v, node)


def fill_ratio(result) -> float:
    vals = [v for _, v in _leaves(result)]
    return sum(v is not None for v in vals) / max(1, len(vals))


def _all_null(x) -> bool:
    if isinstance(x, dict):
        return all(_all_null(v) for v in x.values())
    if isinstance(x, list):
        return all(_all_null(v) for v in x)
    return x is None


# ---------------------------------------------------------------- grounding / transparency
def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, x


def _date_variants(iso: str) -> list[str]:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        return []
    y, mo, d = m.groups()
    names = [k for k, v in N.MONTHS.items() if v == int(mo) and k.endswith(("a", "ia"))]
    out = [f"{d}.{mo}.{y}", f"{int(d)}.{mo}.{y}"]
    out += [f"{int(d)} {n} {y}" for n in names] + [f"{d} {n} {y}" for n in names]
    return out


def ground(doc: P.Document, result: dict, derived: set[str] = frozenset()) -> list[dict]:
    pages = [(p.number, " ".join(p.text.split())) for p in doc.pages]
    digit_pages = []
    for num, t in pages:
        idx = [i for i, c in enumerate(t) if c.isdigit()]
        digit_pages.append((num, t, "".join(t[i] for i in idx), idx))
    ev = []
    for path, val in _leaves(result):
        if val is None:
            continue
        leaf = path.split(".")[-1]
        if leaf in derived:
            ev.append({"field": path, "value": val, "method": "derived"})
            continue
        s = str(val)
        best = None
        if re.fullmatch(r"\d{6,}", s):  # identifiers / accounts: digit-level exact match
            for num, t, dg, idx in digit_pages:
                pos = dg.find(s)
                if pos >= 0:
                    a, b = idx[pos], idx[pos + len(s) - 1] + 1
                    best = (100.0, num, a, b, t)
                    break
        if best is None:
            cands = [s] + _date_variants(s)
            if isinstance(val, float):
                cands.append(f"{val:,.2f}".replace(",", " ").replace(".", ","))
            for c in cands:
                if len(c) < 2:
                    continue
                for num, t in pages:
                    al = fuzz.partial_ratio_alignment(c.lower(), t.lower())
                    if al and (best is None or al.score > best[0]):
                        best = (al.score, num, al.dest_start, al.dest_end, t)
        if best and best[0] >= 80:
            score, num, a, b, t = best
            ev.append({"field": path, "value": val, "page": num, "score": round(score, 1),
                       "quote": t[a:b], "context": t[max(0, a - 80):b + 80], "method": "located"})
        else:
            ev.append({"field": path, "value": val, "method": "inferred",
                       "note": "wartość nie występuje dosłownie w tekście (normalizacja lub wnioskowanie)"})
    return ev


def derived_fields(spec: DocSpec) -> set[str]:
    out = set()

    def walk(props):
        for k, n in props.items():
            if n.get("derive"):
                out.add(k)
            if n["type"] == "object":
                walk(n["properties"])
            elif n["type"] == "array" and n["items"]["type"] == "object":
                walk(n["items"]["properties"])
    walk(spec.fields)
    return out


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
