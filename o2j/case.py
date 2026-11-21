"""Case-level analysis: cross-document consistency checks and safe cross-filling (config/case.yaml).

A case = all documents in one input folder. Checks never change outputs; cross-fill only writes a value into
an empty field when that exact value occurs in the target document's own text (so no guessing).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import yaml
from rapidfuzz import fuzz


def load_case_rules(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def _tokens(path: str):
    return re.findall(r"[^.\[\]]+|\[\*\]|\[\d+\]", path)


def get_all(obj, path: str) -> list:
    cur = [obj]
    for t in _tokens(path):
        nxt = []
        for c in cur:
            if t == "[*]":
                nxt += c if isinstance(c, list) else []
            elif t.startswith("["):
                i = int(t[1:-1])
                if isinstance(c, list) and i < len(c):
                    nxt.append(c[i])
            elif isinstance(c, dict) and t in c:
                nxt.append(c[t])
        cur = nxt
    return [v for v in cur if v not in (None, "", [], {})]


def set_path(obj, path: str, value) -> bool:
    toks = _tokens(path)
    cur = obj
    for i, t in enumerate(toks):
        last = i == len(toks) - 1
        if t.startswith("[") and t != "[*]":
            k = int(t[1:-1])
            if not isinstance(cur, list) or k >= len(cur):
                return False
            if last:
                cur[k] = value
                return True
            cur = cur[k]
        elif isinstance(cur, dict) and t in cur:
            if last:
                cur[t] = value
                return True
            cur = cur[t]
        else:
            return False
    return False


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v)).lower()


def _date(v):
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def _docs_of(case_docs: dict, doctype: str) -> list:
    return [(name, d) for name, d in case_docs.items() if d["doctype"] == doctype]


def run_checks(case_docs: dict, rules: dict) -> list[dict]:
    """case_docs: {filename: {"doctype": str, "result": dict, "text": str}}"""
    out = []
    for c in rules.get("checks", []):
        a_docs = _docs_of(case_docs, c["a"]["doc"])
        b_docs = _docs_of(case_docs, c["b"]["doc"]) if "b" in c else [("", None)]
        rec = {"id": c["id"], "opis": c.get("opis", c["id"]), "status": "n/d", "szczegoly": ""}
        if not a_docs or not b_docs:
            rec["szczegoly"] = "brak dokumentu wymaganego do kontroli"
            out.append(rec)
            continue
        av = [v for _, d in a_docs for v in get_all(d["result"], c["a"]["path"])]
        bv = [v for _, d in b_docs if d for v in get_all(d["result"], c["b"]["path"])] if "b" in c else []
        t = c["type"]
        if t == "value_in":
            w = c.get("when")
            if w and not any(re.search(w["matches"], str(v)) for _, d in _docs_of(case_docs, w["doc"])
                             for v in get_all(d["result"], w["path"])):
                rec["szczegoly"] = "warunek nie dotyczy tej sprawy"
                out.append(rec)
                continue
            if not av:
                rec["szczegoly"] = "brak wartości"
            else:
                ok = all(float(v) in [float(x) for x in c["values"]] for v in av)
                rec.update(status="ok" if ok else "uwaga", szczegoly=f"{av}")
            out.append(rec)
            continue
        if not av or not bv:
            rec["szczegoly"] = "brak wartości w jednym z dokumentów"
            out.append(rec)
            continue
        if t == "equal_any":
            ok = any(_norm(x) == _norm(y) for x in av for y in bv)
        elif t == "fuzzy_any":
            ok = any(fuzz.token_sort_ratio(str(x), str(y)) >= c.get("threshold", 85) for x in av for y in bv)
        elif t == "contains":
            ok = any(_norm(y) in _norm(x) for x in av for y in bv)
        elif t == "date_le":
            tol = timedelta(days=c.get("tolerance_days", 0))
            ok = any(_date(x) and _date(y) and _date(x) <= _date(y) + tol for x in av for y in bv)
        else:
            rec["szczegoly"] = f"nieznany typ kontroli {t}"
            out.append(rec)
            continue
        rec.update(status="ok" if ok else "uwaga", szczegoly=f"{av} ↔ {bv}")
        out.append(rec)
    return out


def cross_fill(case_docs: dict, rules: dict) -> list[dict]:
    """Fill empty target fields from sibling documents when the value literally occurs in the target's text."""
    changes = []
    for r in rules.get("cross_fill", []):
        if r.get("enabled") is False:
            continue
        for tname, td in _docs_of(case_docs, r["target"]["doc"]):
            if get_all(td["result"], r["target"]["path"]):
                continue  # already filled
            text_digits = re.sub(r"\D", "", td.get("text", ""))
            text_norm = _norm(td.get("text", ""))
            for sname, sd in _docs_of(case_docs, r["source"]["doc"]):
                for v in get_all(sd["result"], r["source"]["path"]):
                    sv = str(v)
                    found = (sv.isdigit() and len(sv) >= 6 and sv in text_digits) or (not sv.isdigit() and _norm(sv) in text_norm)
                    if found and set_path(td["result"], r["target"]["path"], v):
                        changes.append({"dokument": tname, "pole": r["target"]["path"], "wartosc": v, "zrodlo": sname})
                        break
                else:
                    continue
                break
    return changes


def analyze_case(case_docs: dict, rules: dict) -> dict:
    fills = cross_fill(case_docs, rules)
    checks = run_checks(case_docs, rules)
    return {"dokumenty": {n: d["doctype"] for n, d in case_docs.items()},
            "uzupelnienia_krzyzowe": fills, "kontrole": checks,
            "podsumowanie": {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "uwaga", "n/d")}}
