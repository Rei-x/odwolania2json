"""Adaptive difficulty router ("auto" profile): cheap first pass, escalate only hard documents.

Signals (generic — nothing learned from a particular dataset):
  * disagreement between two independent extractors: deterministic YAML rules vs LLM (per field)
  * fields still flagged by verification (format / not found in text)
  * OCR / broken text layer used
  * layout novelty: low similarity to the nearest known example (organiser examples + memory)
Escalation re-extracts with stronger model(s) and resolves every field by vote (first pass + strong runs
[+ deterministic rules as a tie-breaking voter]).
"""
from __future__ import annotations

import json

from . import extract as E


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, x


def _n(v):
    return " ".join(str(v).split()).lower() if v is not None else None


def difficulty(llm_result: dict, det_result: dict | None, remaining_issues: list, ocr_used: bool,
               novelty: float | None, cfg: dict) -> dict:
    disputed = []
    if det_result:
        det = dict(_leaves(det_result))
        for path, v in _leaves(llm_result):
            dv = det.get(path)
            if dv is not None and v is not None and _n(dv) != _n(v):
                disputed.append(path)
            elif dv is not None and v is None:
                disputed.append(path)
    flagged = sorted({i["field"] for i in remaining_issues})
    rules = cfg.get("escalate_if") or {}
    reasons = []
    if len(disputed) >= int(rules.get("disputed_fields", 1)):
        reasons.append(f"{len(disputed)} pól różni się między regułami a LLM")
    if len(flagged) >= int(rules.get("remaining_issues", 1)):
        reasons.append(f"{len(flagged)} pól z nierozwiązanymi uwagami weryfikacji")
    if ocr_used and rules.get("ocr", True):
        reasons.append("dokument wymagał OCR")
    if novelty is not None and novelty >= float(rules.get("novelty", 40)):
        reasons.append(f"nowy układ dokumentu (podobieństwo do znanych przykładów {100 - novelty:.0f}%)")
    return {"escalate": bool(reasons), "reasons": reasons, "disputed": disputed, "flagged": flagged,
            "novelty": novelty}


def escalate(pipe, spec, system: str, user: str, images, doc, first: dict, det_result: dict | None,
             cfg: dict) -> tuple[dict, dict]:
    from concurrent.futures import ThreadPoolExecutor

    from .voting import vote
    esc = cfg.get("escalation") or {}
    models = esc.get("models") or [pipe.llm.model]
    n = int(esc.get("n", len(models)))

    def run(i):
        r, _ = pipe.llm.extract_json(system, user, spec.json_schema(), name=spec.name, images=images,
                                     model=models[i % len(models)], temperature=0 if i < len(models) else 0.7)
        return E.postprocess(spec, r)
    with ThreadPoolExecutor(max_workers=n) as ex:
        strong = list(ex.map(run, range(n)))
    voters = strong + [first]  # strong runs first: they win ties
    if det_result and esc.get("include_deterministic", True):
        voters.append(det_result)
    result, info = vote(voters, doc)
    info["models"] = [models[i % len(models)] for i in range(n)] + ["first_pass"] + (
        ["deterministic"] if det_result and esc.get("include_deterministic", True) else [])
    return result, info


def changed_fields(a: dict, b: dict) -> list[dict]:
    da, db = dict(_leaves(a)), dict(_leaves(b))
    return [{"field": k, "before": da.get(k), "after": db.get(k)} for k in sorted(set(da) | set(db))
            if json.dumps(da.get(k), ensure_ascii=False) != json.dumps(db.get(k), ensure_ascii=False)]
