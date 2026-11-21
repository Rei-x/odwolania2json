"""Document classification: weighted keyword rules from YAML, LLM fallback when unsure."""
from __future__ import annotations

import re
from pathlib import Path

from .spec import DocSpec


def _despace(text: str) -> str:
    """'P E Ł N O M O C N I C T W O' -> 'PEŁNOMOCNICTWO' (letter-spaced headings)."""
    return re.sub(r"\b(?:\w ){3,}\w\b", lambda m: m.group(0).replace(" ", ""), text)


def rule_scores(text: str, filename: str, specs: dict[str, DocSpec]) -> dict[str, float]:
    text = _despace(text)
    scores = {}
    fn = filename.lower()
    for name, spec in specs.items():
        s = 0.0
        for pattern, w in (spec.classify.get("keywords") or {}).items():
            if re.search(pattern, text, flags=re.M | re.I):
                s += float(w)
        if any(h in fn for h in spec.classify.get("filename", [])):
            s += 2.0
        scores[name] = s
    return scores


def classify(text: str, path: Path, specs: dict[str, DocSpec], llm=None, min_score: float = 3,
             mode: str = "llm_confirm", model: str | None = None, vote_models: list | None = None,
             use_filename: bool = False) -> tuple[str, dict]:
    """mode: rules (keywords only) | llm_confirm (rules + LLM vote, 'inny' allowed).
    The file name is ignored by default (organiser: file names may be arbitrary)."""
    head = text[:6000]
    scores = rule_scores(head, path.name if use_filename else "", specs)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0
    info = {"method": "rules", "scores": scores}
    confident = best_s >= min_score and best_s - second_s >= 2
    info["confident"] = confident
    if llm is None or (mode == "rules" and confident):
        return (best if best_s > 0 else "inny"), info
    if not head.strip():
        return (best if best_s > 0 else "inny"), info  # nothing to read: rely on filename hint
    names = list(specs) + ["inny"]
    system = ("Klasyfikujesz dokumenty. Wybierz typ WYŁĄCZNIE gdy dokument spełnia definicję typu; "
              "dokumenty jedynie wspominające o odwołaniach, przelewach czy pełnomocnictwach (faktury, prezentacje, "
              "wyroki, wyciągi, korespondencja) to 'inny'. Odpowiedz wyłącznie JSON.")
    opts = "\n".join(f"- {n}: {s.description}" for n, s in specs.items()) + "\n- inny: każdy inny dokument"
    user = f"Typy:\n{opts}\n\nDokument (początek):\n{head[:5000]}\n\nZwróć {{\"typ\": <jeden z {names}>}}."
    schema = {"type": "object", "properties": {"typ": {"enum": names}}, "required": ["typ"], "additionalProperties": False}
    models = [model] + [m for m in (vote_models or []) if m != model]
    choices = []
    for m in models:  # small models disagree sometimes -> vote of rules + models
        try:
            out, _ = llm.extract_json(system, user, schema, name="classification", model=m)
            if out.get("typ") in names:
                choices.append(out["typ"])
        except Exception as e:  # noqa: BLE001
            info.setdefault("llm_errors", []).append(str(e)[:200])
    if not choices:
        return (best if confident else "inny"), info
    votes = choices + ([best] if confident else [])
    from collections import Counter
    cnt = Counter(votes).most_common()
    typ = cnt[0][0] if len(cnt) == 1 or cnt[0][1] > cnt[1][1] else choices[0]  # tie -> primary model
    info.update(method="llm" if not confident else "rules+llm", llm_choice=choices[0], votes=votes)
    return typ, info
