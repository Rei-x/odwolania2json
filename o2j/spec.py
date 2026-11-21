"""Document-class specs loaded from config/doctypes/*.yaml.

A spec declares, without code: how to recognise the class, which fields to
extract (types, descriptions, normalizers, enums) and extra prompt rules.
From it we derive the JSON Schema for constrained decoding, the field guide
for the prompt, and the output skeleton (key order + nulls).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCALARS = {"string", "date", "integer", "number", "enum"}


@dataclass
class DocSpec:
    name: str
    description: str
    classify: dict
    fields: dict  # ordered mapping name -> field node
    instructions: str = ""
    pages: int | None = None  # how many leading pages to send to the LLM
    few_shot: int = 0
    raw: dict = field(default_factory=dict)

    # ---------- JSON schema ----------
    def json_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {k: _schema(v) for k, v in self.fields.items()},
            "required": list(self.fields),
            "additionalProperties": False,
        }

    # ---------- prompt field guide ----------
    def field_guide(self) -> str:
        lines: list[str] = []
        for k, v in self.fields.items():
            _guide(k, v, lines, 0)
        return "\n".join(lines)

    # ---------- output skeleton ----------
    def skeleton(self) -> dict:
        return {k: _empty(v) for k, v in self.fields.items()}


def _schema(node: dict) -> dict:
    t = node["type"]
    desc = node.get("description", "")
    if t == "object":
        props = node["properties"]
        s = {
            "type": "object",
            "properties": {k: _schema(v) for k, v in props.items()},
            "required": list(props),
            "additionalProperties": False,
        }
        if node.get("nullable"):
            s = {"anyOf": [s, {"type": "null"}]}
    elif t == "array":
        s = {"type": "array", "items": _schema(node["items"])}  # never minItems (padding)
    elif t == "enum":
        vals = [e["value"] if isinstance(e, dict) else e for e in node["values"]]
        s = {"anyOf": [{"enum": vals}, {"type": "null"}]}
    else:
        jt = {"string": "string", "date": "string", "integer": "integer", "number": "number"}[t]
        s = {"type": [jt, "null"]}
        if t == "date":
            desc = (desc + " Format YYYY-MM-DD.").strip()
    if desc and "anyOf" not in s:
        s["description"] = desc
    elif desc:
        s = {"description": desc, **s}
    return s


def _guide(name: str, node: dict, lines: list[str], depth: int):
    pad = "  " * depth
    t = node["type"]
    desc = node.get("description", "")
    if t == "object":
        lines.append(f"{pad}- {name} (obiekt){': ' + desc if desc else ''}")
        for k, v in node["properties"].items():
            _guide(k, v, lines, depth + 1)
    elif t == "array":
        lines.append(f"{pad}- {name} (lista){': ' + desc if desc else ''}")
        it = node["items"]
        if it["type"] == "object":
            for k, v in it["properties"].items():
                _guide(k, v, lines, depth + 1)
    elif t == "enum":
        opts = "; ".join(
            f"{e['value']} = {e['label']}" if isinstance(e, dict) else str(e) for e in node["values"]
        )
        lines.append(f"{pad}- {name} (wybór): {desc} Dozwolone: {opts}")
    else:
        lines.append(f"{pad}- {name} ({t}): {desc}")


def _empty(node: dict) -> Any:
    t = node["type"]
    if t == "object":
        return None if node.get("nullable") else {k: _empty(v) for k, v in node["properties"].items()}
    if t == "array":
        return []
    return None


def load_specs(dirpath: Path) -> dict[str, DocSpec]:
    specs = {}
    for p in sorted(dirpath.glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        specs[d["name"]] = DocSpec(
            name=d["name"],
            description=d.get("description", ""),
            classify=d.get("classify", {}),
            fields=d["fields"],
            instructions=d.get("instructions", ""),
            pages=d.get("pages"),
            few_shot=d.get("few_shot", 0),
            raw=d,
        )
    return specs
