"""Learning over time: human-verified results become retrieval examples, corrections drive quality stats
and reviewable rule suggestions. Nothing is fine-tuned; the system improves by remembering.

Layout (data/learned/):
  <doctype>/<sha12>/document.pdf      verified document
  <doctype>/<sha12>/expected.json     verified (possibly corrected) JSON
  <doctype>/<sha12>/meta.json         when, source, which fields were corrected
  feedback.jsonl                      one line per review (field diffs)
  suggestions/<doctype>.md            LLM-proposed YAML instruction lines (for human review)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path

from .case import get_all  # noqa: F401  (re-exported for convenience)


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, x


def diff(predicted: dict, corrected: dict) -> list[dict]:
    p, c = dict(_leaves(predicted or {})), dict(_leaves(corrected or {}))
    return [{"field": k, "before": p.get(k), "after": c.get(k)} for k in sorted(set(p) | set(c)) if p.get(k) != c.get(k)]


class LearningStore:
    def __init__(self, root: Path):
        self.root = root

    def add(self, pdf: Path, doctype: str, predicted: dict, corrected: dict, source: str = "gui") -> dict:
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()[:12]
        d = self.root / doctype / sha
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy(pdf, d / "document.pdf")
        (d / "expected.json").write_text(json.dumps(corrected, ensure_ascii=False, indent=2), encoding="utf-8")
        changes = diff(predicted, corrected)
        n_fields = sum(1 for _ in _leaves(corrected))
        meta = {"ts": time.time(), "doctype": doctype, "source": source, "file": pdf.name,
                "fields": n_fields, "corrected": len(changes), "changes": changes}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "feedback.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({**meta, "id": f"{doctype}/{sha}"}, ensure_ascii=False) + "\n")
        return meta

    def entries(self) -> list[dict]:
        p = self.root / "feedback.jsonl"
        return [json.loads(line) for line in open(p, encoding="utf-8")] if p.exists() else []

    def example_dirs(self, doctype: str) -> list[tuple[Path, Path]]:
        base = self.root / doctype
        if not base.exists():
            return []
        return [(d / "document.pdf", d / "expected.json") for d in sorted(base.iterdir())
                if (d / "document.pdf").exists() and (d / "expected.json").exists()]

    def stats(self) -> dict:
        """Share of fields that needed a human correction, per review batch over time (lower = better)."""
        rows = sorted(self.entries(), key=lambda r: r["ts"])
        timeline, per_field = [], Counter()
        fields = corrected = 0
        for i, r in enumerate(rows, 1):
            fields += r["fields"]
            corrected += r["corrected"]
            for c in r["changes"]:
                per_field[f"{r['doctype']}:{c['field'].split('[')[0]}"] += 1
            timeline.append({"n": i, "ts": r["ts"], "doc_accuracy": 1 - r["corrected"] / max(1, r["fields"]),
                             "cumulative_accuracy": 1 - corrected / max(1, fields)})
        return {"reviews": len(rows), "fields": fields, "corrected": corrected,
                "accuracy": 1 - corrected / max(1, fields) if rows else None,
                "timeline": timeline, "most_corrected": per_field.most_common(10),
                "examples": {d.name: len(list(d.iterdir())) for d in self.root.iterdir()
                             if d.is_dir() and d.name != "suggestions"} if self.root.exists() else {}}

    def suggest_rules(self, llm, specs: dict, min_count: int = 2) -> dict[str, str]:
        """Group repeated corrections per field and ask the LLM for instruction lines (written for review)."""
        groups = defaultdict(list)
        for r in self.entries():
            for c in r["changes"]:
                groups[(r["doctype"], c["field"].split("[")[0])].append(c)
        out = {}
        by_type = defaultdict(list)
        for (dt, field), cs in groups.items():
            if len(cs) >= min_count:
                by_type[dt].append((field, cs[:8]))
        for dt, items in by_type.items():
            if dt not in specs:
                continue
            listing = "\n".join(f"- pole {f}: " + "; ".join(f"{c['before']!r} → {c['after']!r}" for c in cs)
                                for f, cs in items)
            system = "Jesteś inżynierem konfiguracji systemu ekstrakcji danych. Odpowiadasz wyłącznie JSON."
            user = (f"Obecne reguły dla typu '{dt}':\n{specs[dt].instructions}\n\n"
                    f"Użytkownicy wielokrotnie poprawiali wyniki ekstrakcji:\n{listing}\n\n"
                    "Zaproponuj krótkie, ogólne reguły (po polsku) do dopisania w sekcji instructions pliku YAML, "
                    "które zapobiegną tym błędom. Nie powtarzaj istniejących reguł. "
                    'Zwróć {"reguly": ["- ...", ...], "uzasadnienie": "..."}')
            schema = {"type": "object", "properties": {"reguly": {"type": "array", "items": {"type": "string"}},
                                                       "uzasadnienie": {"type": "string"}},
                      "required": ["reguly", "uzasadnienie"], "additionalProperties": False}
            res, _ = llm.extract_json(system, user, schema, name="rule_suggestions")
            md = (f"# Propozycje reguł dla `{dt}` (do przeglądu)\n\nNa podstawie poprawek:\n{listing}\n\n"
                  "## Proponowane linie do `instructions`\n" + "\n".join(res.get("reguly", [])) +
                  f"\n\n## Uzasadnienie\n{res.get('uzasadnienie', '')}\n")
            p = self.root / "suggestions" / f"{dt}.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            out[dt] = str(p)
        return out
