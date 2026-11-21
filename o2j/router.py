"""Adaptive difficulty router ("auto" profile): cheap first pass, escalate only hard documents.

Signals (generic — nothing learned from a particular dataset):
  * disagreement between two independent extractors: deterministic YAML rules vs LLM (per field)
  * fields still flagged by verification (format / not found in text)
  * OCR / broken text layer used (off in profile `auto`: scans go straight to `router.scan_model`)
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


def remaining_levels(cfg: dict, first_model: str | None) -> list[list[str]]:
    """Escalation levels still above the model that ran the first pass (all levels for the default model).
    A first pass on the scan model skips the levels up to and including the one made of that model alone."""
    esc = cfg.get("escalation") or {}
    levels = [lv if isinstance(lv, list) else [lv] for lv in (esc.get("levels") or [])]
    if first_model is None:
        return levels
    for i in range(len(levels) - 1, -1, -1):
        if levels[i] == [first_model]:
            return levels[i + 1:]
    return levels


def escalate(pipe, spec, system: str, user: str, images, doc, first: dict, det_result: dict | None,
             cfg: dict) -> tuple[dict, dict]:
    """Cascade: climb model levels (cheap -> strong) until the new level agrees with the current consensus.
    Every level's runs join the vote; deterministic rules act as an extra (tie-breaking) voter."""
    from concurrent.futures import ThreadPoolExecutor

    from .tracing import bind
    from .voting import vote
    esc = cfg.get("escalation") or {}
    levels = esc.get("levels") or [esc.get("models") or [pipe.llm.model]]
    use_det = bool(det_result) and esc.get("include_deterministic", True)
    pool, steps = [first], []
    consensus = first
    for li, models in enumerate(levels):
        models = models if isinstance(models, list) else [models]

        def run(m):
            r, _ = pipe.llm.extract_json(system, user, spec.json_schema(), name=spec.name, images=images,
                                         model=m, temperature=0)
            return E.postprocess(spec, r)
        with ThreadPoolExecutor(max_workers=len(models)) as ex:
            runs = list(ex.map(bind(run), models))
        level_view = runs[0] if len(runs) == 1 else vote(runs, doc)[0]
        disagree = [c["field"] for c in changed_fields(consensus, level_view)]
        pool = runs + pool  # newest (stronger) runs first: they win ties
        consensus, info = vote(pool + ([det_result] if use_det else []), doc)
        steps.append({"level": li + 1, "models": models, "disagreed_with_previous": disagree})
        if not disagree:  # stronger level confirms the consensus -> stop climbing
            break
    return consensus, {"steps": steps, "voters": len(pool) + (1 if use_det else 0)}


def changed_fields(a: dict, b: dict) -> list[dict]:
    da, db = dict(_leaves(a)), dict(_leaves(b))
    return [{"field": k, "before": da.get(k), "after": db.get(k)} for k in sorted(set(da) | set(db))
            if json.dumps(da.get(k), ensure_ascii=False) != json.dumps(db.get(k), ensure_ascii=False)]
