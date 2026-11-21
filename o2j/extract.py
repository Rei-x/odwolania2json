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
- Imiona i nazwiska osób ZAWSZE w mianowniku, bez tytułów, nawet gdy w dokumencie są odmienione ("udzielam pełnomocnictwa Janowi Kowalskiemu" → "Jan Kowalski"; "przez r.pr. Klaudię Nowak" → "Klaudia Nowak"). Zasada wiernego przepisywania dotyczy pisowni, nie przypadka.
- Daty względne ("br.", "tego samego dnia", "dnia dwunastego czerwca") zamieniaj na pełną datę YYYY-MM-DD na podstawie kontekstu dokumentu (rok z daty pisma).
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


def few_shot_examples(spec: DocSpec, train_dir: Path, query_text: str, exclude: set[str], k: int,
                      learned: list[tuple[Path, Path]] | None = None, scores_out: list | None = None,
                      names_out: list | None = None) -> list[tuple[str, str]]:
    """Most similar verified examples: organiser training data + documents verified by users (memory)."""
    ex = spec.raw.get("examples") or {}
    if not k:
        return []
    cands = []
    if not ex or not train_dir or not train_dir.exists():
        train_dir = None
    names = (ex.get("pdf") if isinstance(ex.get("pdf"), list) else [ex.get("pdf")]) if ex else []
    for case in (sorted(p for p in train_dir.iterdir() if p.is_dir()) if train_dir else []):
        pdf = next((case / n for n in names if (case / n).exists()), None)
        js = case / ex["json"]
        if case.name in exclude or pdf is None or not js.exists():
            continue
        cands.append((case.name, pdf, js))
    LEARNED_BONUS = 5.0  # human-verified examples (often real-world layouts) are slightly preferred
    for pdf, js in (learned or []):
        cands.append(("learned:" + pdf.parent.name, pdf, js))
    q = query_text[:3000]
    scored = []
    for name, pdf, js in cands:
        t = _example_text(str(pdf), spec.pages)
        bonus = LEARNED_BONUS if name.startswith("learned:") else 0.0
        if name.startswith("learned:") and t[:3000] == q:  # never use the very same document as its own example
            continue
        scored.append((fuzz.ratio(q, t[:3000]) + bonus, name, t, js))
    scored.sort(key=lambda x: -x[0])
    if scores_out is not None:
        scores_out.extend(round(x[0], 1) for x in scored[:k])
    if names_out is not None:
        names_out.extend(x[1] for x in scored[:k])
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
        res = [r for r in (_pp(node["items"], it, None) for it in items) if not _all_null(r)]
        if node.get("dedupe") == "person":
            res = _dedupe_people(res)
        return res
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


def _person_key(item):
    name = next((v for v in (item.values() if isinstance(item, dict) else [item]) if isinstance(v, str)), None)
    if not name:
        return None
    toks = name.lower().split()
    return (toks[0], toks[-1]) if len(toks) >= 2 else tuple(toks)


def _dedupe_people(items: list) -> list:
    """'Paweł Wierzowiecki' (signature block) and 'Paweł Stanisław Wierzowiecki' (e-signature stamp) are one person."""
    out, seen = [], {}
    for it in items:
        k = _person_key(it)
        if k is None or k not in seen:
            if k is not None:
                seen[k] = len(out)
            out.append(it)
    return out


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
    gen = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
           "października", "listopada", "grudnia"][int(mo) - 1]
    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][int(mo) - 1]
    out = [f"{d}.{mo}.{y}", f"{int(d)}.{mo}.{y}", f"{d}-{mo}-{y}", f"{d}/{mo}/{y}",
           f"{int(d)} {gen} {y}", f"{d} {gen} {y}", f"{int(d)} {roman} {y}", f"{int(d)} {gen}"]
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
            m = re.fullmatch(r"(\d{5,7})-(\d{4})", s)  # TED 'NNNNNN-YYYY' may appear as 'YYYY/S ###-NNNNNN'
            if m:
                cands.append(f"{m.group(2)}/S")
                cands.insert(1, m.group(1))
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


# ---------------------------------------------------------------- snap-to-text (small-model copy errors)
def _walk_leaves(props: dict, value, path=""):
    value = value if isinstance(value, dict) else {}
    for k, node in props.items():
        p = f"{path}.{k}" if path else k
        v = value.get(k)
        if node["type"] == "object":
            yield from _walk_leaves(node["properties"], v, p)
        elif node["type"] == "array" and node["items"]["type"] == "object":
            for i, it in enumerate(v or []):
                yield from _walk_leaves(node["items"]["properties"], it, f"{p}[{i}]")
        else:
            yield p, node, v


def _set_leaf(result, path, value):
    toks = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cur = result
    for t in toks[:-1]:
        cur = cur[int(t[1:-1])] if t.startswith("[") else cur[t]
    last = toks[-1]
    if last.startswith("["):
        cur[int(last[1:-1])] = value
    else:
        cur[last] = value


def snap_to_text(spec: DocSpec, result: dict, doc: P.Document) -> list[dict]:
    """Correct small copy errors of the LLM using the document text (generic, no dataset knowledge):
    * identifiers: model digits are a fragment of a longer digit run in the text that satisfies the field
      pattern (e.g. 24 of 26 account digits) -> take the full run;
    * strings (e-mail, names, numbers with letters): value not found verbatim, but a near-identical span
      (similarity >= 92, same length +-2) exists -> take the exact span from the document.
    Returns the list of changes (logged in the trace for transparency)."""
    text = " ".join(" ".join(p.text.split()) for p in doc.pages)
    if not text:
        return []
    low = text.lower()
    digit_runs = re.findall(r"\d[\d ]{5,40}\d", text)
    changes = []
    for path, node, v in _walk_leaves(spec.fields, result):
        if v is None or node.get("derive") or node["type"] in ("enum", "integer", "number", "date"):
            continue
        if "person" in (node.get("normalize") or []):
            continue  # names are legitimately in nominative while the text declines them
        s = str(v)
        pat = node.get("pattern")
        if re.fullmatch(r"\d{6,}", s):
            if pat and re.fullmatch(pat, s):
                continue
            for run in digit_runs:
                d = re.sub(r"\D", "", run)
                if s in d and d != s and (not pat or re.fullmatch(pat, d)):
                    changes.append({"field": path, "before": s, "after": d, "rule": "digits-extended"})
                    _set_leaf(result, path, N.apply(d, node))
                    break
            continue
        if s.lower() in low or len(s) < 5:
            continue
        al = fuzz.partial_ratio_alignment(s.lower(), low)
        if not al or al.score < 92:
            continue
        a, b = al.dest_start, al.dest_end
        # extend to token boundaries
        while a > 0 and not text[a - 1].isspace() and text[a - 1] not in "(:;,„\"":
            a -= 1
        while b < len(text) and not text[b].isspace() and text[b] not in "),;”\"":
            b += 1
        span = text[a:b].strip(" .,;:")
        if abs(len(span) - len(s)) > 2 or span == s:
            continue
        fixed = N.apply(span, node)
        if pat and fixed and not re.fullmatch(pat, str(fixed)):
            continue
        changes.append({"field": path, "before": s, "after": fixed, "rule": "snapped-to-text"})
        _set_leaf(result, path, fixed)
    return changes


def rules_fill(spec: DocSpec, result: dict, det: dict | None, doc: P.Document) -> list[dict]:
    """Fill fields the LLM left empty with deterministic-rule values that are literally present in the text."""
    if not det:
        return []
    text = " ".join(" ".join(p.text.split()) for p in doc.pages).lower()
    detv = {p: v for p, _, v in _walk_leaves(spec.fields, det)}
    changes = []
    for path, node, v in _walk_leaves(spec.fields, result):
        dv = detv.get(path)
        if v is not None or dv is None or node.get("derive"):
            continue
        pat = node.get("pattern")
        if pat and not re.fullmatch(pat, str(dv)):
            continue
        if str(dv).lower() not in text and re.sub(r"\D", "", str(dv)) not in re.sub(r"\D", "", text):
            continue
        _set_leaf(result, path, dv)
        changes.append({"field": path, "before": None, "after": dv, "rule": "rules-fill"})
    return changes
