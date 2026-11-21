"""Document classification: weighted keyword rules from YAML, LLM fallback when unsure."""
from __future__ import annotations

import re
from pathlib import Path

from .spec import DocSpec


def rule_scores(text: str, filename: str, specs: dict[str, DocSpec]) -> dict[str, float]:
    scores = {}
    fn = filename.lower()
    for name, spec in specs.items():
        s = 0.0
        for pattern, w in (spec.classify.get("keywords") or {}).items():
            if re.search(pattern, text, flags=re.M):
                s += float(w)
        if any(h in fn for h in spec.classify.get("filename", [])):
            s += 2.0
        scores[name] = s
    return scores


def classify(text: str, path: Path, specs: dict[str, DocSpec], llm=None, min_score: float = 3) -> tuple[str, dict]:
    head = text[:6000]
    scores = rule_scores(head, path.name, specs)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0
    info = {"method": "rules", "scores": scores}
    if (best_s >= min_score and best_s - second_s >= 2) or llm is None:
        return best, info
    # uncertain -> ask the LLM
    names = list(specs) + ["inny"]
    system = "Klasyfikujesz polskie dokumenty urzędowe. Odpowiedz wyłącznie JSON."
    opts = "\n".join(f"- {n}: {s.description}" for n, s in specs.items()) + "\n- inny: żaden z powyższych"
    user = f"Typy dokumentów:\n{opts}\n\nDokument (początek):\n{head[:4000]}\n\nZwróć {{\"typ\": <jeden z {names}>}}."
    schema = {"type": "object", "properties": {"typ": {"enum": names}}, "required": ["typ"], "additionalProperties": False}
    try:
        out, meta = llm.extract_json(system, user, schema, name="classification")
        typ = out.get("typ")
        if typ in names:
            info.update(method="llm", llm_choice=typ)
            return typ, info
    except Exception as e:  # noqa: BLE001
        info["llm_error"] = str(e)
    return best, info
