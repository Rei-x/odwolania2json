"""Agentic verify -> repair loop.

verify(): deterministic checks driven by the doctype YAML
  - `pattern`: regex the normalised value must match (e.g. NIP = 10 digits)
  - `single_person: true`: field must hold one person, not a list of names
  - grounding: literal fields whose value cannot be found in the document text
  - schema-level: enum fields left empty while the doc has text
repair(): sends only the flagged fields + issues back to the LLM with the document,
  merges corrections for those fields only, then re-verifies (bounded rounds).
"""
from __future__ import annotations

import json
import re

from . import extract as E

LITERAL_TYPES = {"string", "date", "integer", "number"}


def _walk(props: dict, value, path: str, out: list):
    value = value if isinstance(value, dict) else {}
    for k, node in props.items():
        p = f"{path}.{k}" if path else k
        v = value.get(k)
        t = node["type"]
        if t == "object":
            _walk(node["properties"], v, p, out)
        elif t == "array":
            for i, it in enumerate(v or []):
                if node["items"]["type"] == "object":
                    _walk(node["items"]["properties"], it, f"{p}[{i}]", out)
                else:
                    out.append((f"{p}[{i}]", node["items"], it))
        else:
            out.append((p, node, v))


def verify(spec, result: dict, evidence: list[dict]) -> list[dict]:
    ev = {e["field"]: e for e in evidence}
    issues = []
    leaves: list = []
    _walk(spec.fields, result, "", leaves)
    for path, node, v in leaves:
        if v is None or node.get("derive"):
            continue
        pat = node.get("pattern")
        if pat and not re.fullmatch(pat, str(v)):
            issues.append({"field": path, "value": v, "issue": f"niepoprawny format (oczekiwany wzorzec {pat})"})
            continue
        if node.get("single_person") and re.search(r",|\s+i\s+|\s+oraz\s+|;", str(v)):
            issues.append({"field": path, "value": v,
                           "issue": "pole musi zawierać dokładnie jedną osobę (pierwszą wskazaną), a nie listę"})
            continue
        literal = node.get("literal", node["type"] in LITERAL_TYPES and not node.get("normalize") == ["integer"])
        e = ev.get(path)
        if literal and node["type"] != "integer" and e and e.get("method") == "inferred":
            issues.append({"field": path, "value": v,
                           "issue": "wartości nie znaleziono w treści dokumentu — sprawdź czy jest przepisana wiernie lub czy w ogóle występuje (jeśli nie — null)"})
    return issues


REPAIR_SYSTEM = """Jesteś weryfikatorem ekstrakcji danych z polskich dokumentów prawnych.
Otrzymujesz dokument, wynik wcześniejszej ekstrakcji oraz listę pól, które automatyczna walidacja oznaczyła jako podejrzane.
Dla KAŻDEGO wskazanego pola ponownie przeanalizuj dokument i zwróć poprawioną wartość (albo tę samą, jeśli była poprawna; null jeśli informacji nie ma).
Zasady pól:
{guide}

Reguły szczegółowe:
{instructions}

Zwróć JSON: {{"poprawki": [{{"field": "<ścieżka pola dokładnie jak w liście>", "value": <wartość lub null>, "uzasadnienie": "<krótko, z cytatem z dokumentu>"}}]}}"""


def _set(result: dict, path: str, value):
    parts = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cur = result
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return False
            if last:
                cur[idx] = value
            else:
                cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return False
            if last:
                cur[part] = value
            else:
                cur = cur[part]
    return True


def repair(llm, spec, doc_text: str, result: dict, issues: list[dict]) -> tuple[dict, list[dict]]:
    system = REPAIR_SYSTEM.format(guide=spec.field_guide(), instructions=spec.instructions.strip() or "-")
    user = (f"### DOKUMENT\n{doc_text}\n\n### WYNIK EKSTRAKCJI\n{E.dumps(result)}\n\n"
            f"### PODEJRZANE POLA\n" + "\n".join(f"- {i['field']} = {json.dumps(i['value'], ensure_ascii=False)}: {i['issue']}"
                                                   for i in issues))
    schema = {"type": "object", "properties": {"poprawki": {"type": "array", "items": {
        "type": "object", "properties": {"field": {"type": "string"},
                                         "value": {"type": ["string", "number", "integer", "null"]},
                                         "uzasadnienie": {"type": "string"}},
        "required": ["field", "value", "uzasadnienie"], "additionalProperties": False}}},
        "required": ["poprawki"], "additionalProperties": False}
    out, _ = llm.extract_json(system, user, schema, name="repair")
    flagged = {i["field"] for i in issues}
    raw = json.loads(json.dumps(result))
    changes = []
    for fix in out.get("poprawki", []):
        f = fix.get("field")
        if f not in flagged:
            continue
        before = _get(raw, f)
        if _set(raw, f, fix.get("value")):
            changes.append({"field": f, "before": before, "after": fix.get("value"),
                            "reason": fix.get("uzasadnienie")})
    # re-run normalisation over the merged result
    return E.postprocess(spec, raw), changes


def _get(result, path):
    cur = result
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        try:
            cur = cur[int(part[1:-1])] if part.startswith("[") else cur[part]
        except (KeyError, IndexError, TypeError):
            return None
    return cur
