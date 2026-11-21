"""Kreator nowego typu dokumentu (GUI): szablon JSON / tabela pól -> YAML specyfikacji, walidacja, podgląd.

Nic tu nie zmienia potoku: wynikiem jest plik config/doctypes/<nazwa>.yaml w tym samym formacie,
który czyta o2j.spec.load_specs. Moduł nie woła LLM (podpowiedzi to proste heurystyki).
"""
from __future__ import annotations

import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from .normalize import NORMALIZERS
from .spec import SCALARS, load_specs

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
BUILTIN = {"odwolanie", "pelnomocnictwo", "przelew"}
TYPES = SCALARS | {"object", "array"}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_INSTRUCTIONS = """- Wartości przepisuj wiernie z dokumentu; brak informacji = null.
- Daty w formacie YYYY-MM-DD, kwoty jako liczby, numery identyfikacyjne bez spacji.
"""


# ============================================================ tolerant JSON-with-comments parser
class TemplateError(ValueError):
    def __init__(self, msg: str, line: int | None = None):
        super().__init__(msg)
        self.line = line


_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r\n]+)
  | (?P<comment>//[^\n]*|/\*.*?\*/|\#[^\n]*)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<num>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<lit>true|false|null)
  | (?P<punct>[{}\[\]:,])
""", re.X | re.S)


def _tokens(text: str) -> list[tuple[str, Any, int]]:
    out, pos, line = [], 0, 1
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise TemplateError(f"Nieoczekiwany znak {text[pos]!r}", line)
        kind, val = m.lastgroup, m.group()
        if kind == "comment":
            body = val[2:-2] if val.startswith("/*") else val.lstrip("/#")
            out.append(("comment", " ".join(body.split()), line))
        elif kind == "str":
            import json
            out.append(("str", json.loads(val), line))
        elif kind == "num":
            out.append(("num", float(val) if any(c in val for c in ".eE") else int(val), line))
        elif kind == "lit":
            out.append(("lit", {"true": True, "false": False, "null": None}[val], line))
        elif kind == "punct":
            out.append((val, val, line))
        line += val.count("\n")
        pos = m.end()
    return out


class _P:
    """Recursive-descent parser; commas optional (the organiser's templates sometimes miss them).
    Produces nodes: ("obj", [(key, node, comment)]), ("arr", [node]), ("val", python_value)."""

    def __init__(self, toks):
        self.t, self.i, self.pending = toks, 0, []

    def _skip(self):
        while self.i < len(self.t) and self.t[self.i][0] == "comment":
            self.pending.append(self.t[self.i])
            self.i += 1

    def peek(self):
        self._skip()
        return self.t[self.i] if self.i < len(self.t) else ("eof", None, self.t[-1][2] if self.t else 1)

    def take(self, kind=None):
        tok = self.peek()
        if kind and tok[0] != kind:
            raise TemplateError(f"Oczekiwano {kind!r}, jest {tok[1]!r}", tok[2])
        self.i += 1
        return tok

    def trailing(self, line):
        """Comment on the same line right after a value (optionally after its comma) describes that value."""
        if self.i < len(self.t) and self.t[self.i][0] == "," and self.t[self.i][2] == line:
            self.i += 1
        txt = []
        while self.i < len(self.t) and self.t[self.i][0] == "comment" and self.t[self.i][2] == line:
            txt.append(self.t[self.i][1])
            self.i += 1
        return " ".join(txt)

    def value(self):
        tok = self.peek()
        if tok[0] == "{":
            return self.obj()
        if tok[0] == "[":
            return self.arr()
        if tok[0] in ("str", "num", "lit"):
            self.take()
            return ("val", tok[1]), tok[2]
        raise TemplateError(f"Oczekiwano wartości, jest {tok[1]!r}", tok[2])

    def obj(self):
        self.take("{")
        self.pending = []
        items = []
        while True:
            tok = self.peek()
            if tok[0] == "}":
                self.take()
                break
            if tok[0] == ",":
                self.take()
                continue
            if tok[0] != "str":
                raise TemplateError(f"Oczekiwano nazwy pola w cudzysłowie, jest {tok[1]!r}", tok[2])
            before = " ".join(c[1] for c in self.pending)
            self.pending = []
            key = self.take()[1]
            self.take(":")
            node, end_line = self.value()
            after = self.trailing(end_line)
            items.append((key, node, " ".join(x for x in (before, after) if x).strip()))
            self.pending = []
        return ("obj", items), self.t[self.i - 1][2]

    def arr(self):
        self.take("[")
        items = []
        while True:
            tok = self.peek()
            if tok[0] == "]":
                self.take()
                break
            if tok[0] == ",":
                self.take()
                continue
            node, end_line = self.value()
            self.trailing(end_line)
            items.append(node)
        self.pending = []
        return ("arr", items), self.t[self.i - 1][2]


def parse_template(text: str):
    toks = _tokens(text)
    if not [t for t in toks if t[0] != "comment"]:
        raise TemplateError("Szablon jest pusty", 1)
    p = _P(toks)
    node, _ = p.value()
    rest = p.peek()
    if rest[0] != "eof":
        raise TemplateError(f"Nadmiarowa treść po zamknięciu szablonu: {rest[1]!r}", rest[2])
    if node[0] != "obj":
        raise TemplateError("Szablon musi być obiektem JSON {…}", 1)
    return node


# ============================================================ field-name heuristics
def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).replace("ł", "l").replace("Ł", "L")


# (regex on folded lower-case field name) -> overrides
NAME_RULES: list[tuple[str, dict]] = [
    (r"(^|_)nip($|_)", {"normalize": ["nip"], "pattern": r"\d{10}", "type": "string"}),
    (r"(^|_)krs($|_)", {"normalize": ["krs"], "pattern": r"\d{10}", "type": "string"}),
    (r"(^|_)regon($|_)", {"normalize": ["regon"], "pattern": r"\d{9}(\d{5})?", "type": "string"}),
    (r"(^|_)pesel($|_)", {"normalize": ["pesel"], "type": "integer"}),
    (r"iban|rachun|(^|_)konto|nr_konta|numer_konta", {"normalize": ["iban"], "pattern": r"\d{26}", "type": "string"}),
    (r"(^|_)bzp($|_)", {"normalize": ["bzp"], "type": "string"}),
    (r"(^|_)ted($|_)", {"normalize": ["ted"], "type": "string"}),
    (r"^data($|_)|_data$|(^|_)dzien($|_)|termin", {"normalize": ["date"], "type": "date"}),
    (r"kwota|wartosc|cena|brutto|netto|(^|_)vat($|_)|oplata|wpis|naleznosc|saldo", {"normalize": ["amount"], "type": "number"}),
    (r"imie_nazwisko|imie_i_nazwisko|(^|_)nazwisko|(^|_)osoba($|_)", {"normalize": ["person"], "single_person": True, "type": "string"}),
    (r"miejscowosc|(^|_)miasto($|_)", {"normalize": ["city"], "type": "string"}),
]
PERSON_LIST = re.compile(r"pelnomocni|podpisuj|osoby|czlonk|reprezent|sklad")


def suggest(name: str) -> dict:
    """Normaliser / type / validator suggestions from the field name alone."""
    key = fold(name).lower()
    for rx, over in NAME_RULES:
        if re.search(rx, key):
            return dict(over)
    return {}


def _enum_from_comment(comment: str, example) -> list | None:
    """'1- tak, 0- nie' / '1=Decyzja…, 2=…' / '"osoba_prawna" lub "osoba_fizyczna"' -> enum values."""
    num = re.findall(r"(?:^|[\s,;(:])(\d{1,3})\s*[=\-–:]\s*([^,;=]+?)(?=\s*(?:[,;]|\blub\b|\balbo\b)\s*\d{1,3}\s*[=\-–:]|\s*[.;]?\s*$)", comment)
    if len(num) >= 2 and len({n for n, _ in num}) == len(num):
        return [{"value": int(n), "label": lab.strip(" .")} for n, lab in num]
    quoted = re.findall(r"[\"'„]([A-Za-z0-9_\-]+)[\"'”]", comment)
    if len(quoted) >= 2 and (example is None or example in quoted) and re.search(r"\blub\b|\balbo\b|\bor\b|,|/", comment):
        return list(dict.fromkeys(quoted))
    return None


def _infer(name: str, node, comment: str) -> dict:
    kind = node[0]
    out: dict = {}
    if kind == "obj":
        out = {"type": "object", "properties": _props(node[1])}
    elif kind == "arr":
        items = node[1]
        objs = [it for it in items if it[0] == "obj"]
        if objs:  # union of keys of all example items, first-seen order
            merged: list = []
            seen: dict = {}
            for o in objs:
                for k, v, c in o[1]:
                    if k not in seen:
                        seen[k] = len(merged)
                        merged.append((k, v, c))
                    elif merged[seen[k]][1] == ("val", None) and v != ("val", None):
                        merged[seen[k]] = (k, v, merged[seen[k]][2] or c)
            out = {"type": "array", "items": {"type": "object", "properties": _props(merged)}}
            props = out["items"]["properties"]
            if PERSON_LIST.search(fold(name).lower()) or any(
                    (p.get("normalize") or [None])[0] == "person" for p in props.values()):
                out["dedupe"] = "person"
        else:
            sample = next((it for it in items if it[0] == "val" and it[1] is not None), ("val", None))
            out = {"type": "array", "items": _scalar(name, sample[1], "")}
    else:
        out = _scalar(name, node[1], comment)
    if comment:
        out = {**out, "description": comment} if out["type"] not in ("object", "array") else {"description": comment, **out}
    return out


def _scalar(name: str, v, comment: str) -> dict:
    enum = _enum_from_comment(comment, v) if comment else None
    if enum:
        return {"type": "enum", "values": enum}
    if isinstance(v, bool):
        t = "integer"
    elif isinstance(v, int):
        t = "integer"
    elif isinstance(v, float):
        t = "number"
    elif isinstance(v, str) and ISO_DATE.match(v):
        t = "date"
    else:
        t = "string"
    node = {"type": t}
    s = suggest(name)
    if s:
        st = s.pop("type", None)
        # value type wins over the name hint, except for null / string examples (template often has null)
        if st and (v is None or (isinstance(v, str) and st in ("date", "string"))
                   or (st == "number" and isinstance(v, int)) or (st == "integer" and isinstance(v, int))):
            node["type"] = st
        if node["type"] in ("string", st):
            node.update(s)
        elif node["type"] == "integer" and s.get("normalize") == ["pesel"]:
            node.update(s)
    return node


def _props(items) -> dict:
    return {k: _infer(k, v, c) for k, v, c in items}


def fields_from_template(text: str) -> dict:
    return _props(parse_template(text)[1])


# ============================================================ field table (GUI) -> fields
def fields_from_table(rows: list[dict]) -> dict:
    """rows: [{name, type, description, normalize, values, children}] where type is one of
    string|date|integer|number|enum|object|array (list of objects)|array_string (list of texts)."""
    out: dict = {}
    for r in rows or []:
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        t = r.get("type") or "string"
        desc = str(r.get("description") or "").strip()
        norm = r.get("normalize") or "auto"
        if t == "object":
            node = {"type": "object", "properties": fields_from_table(r.get("children") or [])}
        elif t == "array":
            node = {"type": "array", "items": {"type": "object", "properties": fields_from_table(r.get("children") or [])}}
            if PERSON_LIST.search(fold(name).lower()):
                node["dedupe"] = "person"
        elif t == "array_string":
            node = {"type": "array", "items": {"type": "string"}}
        else:
            node = {"type": t}
            if t == "enum":
                node["values"] = _parse_values(r.get("values") or "")
            if norm == "auto" and t != "enum":
                s = suggest(name)
                st = s.pop("type", None)
                if st == t or (t == "string" and st in (None, "string")):
                    node.update(s)
            elif norm not in ("auto", "none", ""):
                node["normalize"] = [norm]
        if desc:
            node = {"type": node["type"], "description": desc, **{k: v for k, v in node.items() if k != "type"}}
        out[name] = node
    return out


def _parse_values(s) -> list:
    if isinstance(s, list):
        return s
    vals = []
    for part in re.split(r"[,;\n]", str(s)):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([^=]+?)\s*=\s*(.+)$", part)
        if m:
            v = m.group(1).strip()
            vals.append({"value": int(v) if v.lstrip("-").isdigit() else v, "label": m.group(2).strip()})
        else:
            vals.append(int(part) if part.lstrip("-").isdigit() else part)
    return vals


# ============================================================ classification hints
STOP = set("""a aby albo ale ani bez bo by być co czy dla do i id ich ile im jak jako je jego jej jest jeśli już
lub ma mu na nad nie niż o od oraz po pod przez przy się są ta tak te ten to tu tylko w we wraz z za ze że który która
które którym którego dokument dokumentu dokumencie pismo pisma postępowania sprawie zawiera zwykle wskazanym wskazane
oraz rzecz także jego jej ich danych dane danymi""".split())
# words frequent in every document of this domain: useless (or harmful) as class evidence
DOMAIN_COMMON = ("zamawiaj", "odwołuj", "wykonaw", "strony", "stronie", "postępow", "zamówie", "publiczn", "krajowej",
                 "izby", "izbie", "tocz", "odwoław", "zgłasza", "podmiot", "przed", "któr", "osoby", "osoba")


def suggest_classify(name: str, title: str, description: str) -> dict:
    """Weighted keyword regexes + filename hints from the document title / description (no LLM)."""
    title = (title or "").strip()
    words = [w for w in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", title) if w.lower() not in STOP]
    kw: dict[str, int] = {}
    if words:
        head = words[0]
        # heading: upper-case word at the start of a line (case-sensitive), e.g. "PRZYSTĄPIENIE DO ..." / "FAKTURA VAT";
        # a case-insensitive match anywhere would also fire on rulings and letters that merely mention the document
        kw[rf"^\s*(?-i:{head.upper()})\b"] = 5
        if len(words) > 1:
            phrase = r"\s+(?:\w+\s+){0,2}".join(re.escape(w.lower()[:max(5, len(w) - 3)]) + r"\w*" for w in words[:3])
            kw[phrase] = 2
    seen = {fold(w.lower())[:5] for w in words}
    desc_words = [w for w in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{6,}", description or "")
                  if w.lower() not in STOP and not w.lower().startswith(DOMAIN_COMMON)]
    for w in desc_words:
        stem = w.lower()[:max(5, len(w) - 3)]
        if fold(stem)[:5] in seen:
            continue
        seen.add(fold(stem)[:5])
        kw[rf"\b{stem}\w*"] = 1
        if len(kw) >= 5:
            break
    fn = []
    for w in [name.replace("_", " ")] + words[:1]:
        f = fold(w.lower()).split()
        if f and len(f[0]) >= 4:
            fn.append(f[0][:max(5, len(f[0]) - 3)])
    return {"keywords": kw, "filename": list(dict.fromkeys(fn))}


# ============================================================ YAML rendering (readable, like the built-in files)
def _q(v) -> str:
    """Flow-style YAML for a value, safe inside a flow mapping ({k: v, ...}); strings are quoted when needed."""
    if isinstance(v, str):
        plain = yaml.safe_dump(v, allow_unicode=True, width=10 ** 6).strip().removesuffix("...").strip()
        try:
            if yaml.safe_load("{k: " + plain + "}") == {"k": v} and "\n" not in plain:
                return plain
        except yaml.YAMLError:
            pass
        return "'" + v.replace("'", "''") + "'" if "\n" not in v else yaml.safe_dump(v, allow_unicode=True, default_style='"').strip()
    if isinstance(v, list):
        return "[" + ", ".join(_q(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_q(str(k))}: {_q(x)}" for k, x in v.items()) + "}"
    return yaml.safe_dump(v, default_flow_style=True).strip().removesuffix("...").strip()


def _leaf(node: dict) -> str:
    order = ["type", "normalize", "pattern", "single_person", "values", "derive", "description"]
    keys = [k for k in order if k in node] + [k for k in node if k not in order]
    return "{" + ", ".join(f"{k}: {_q(node[k])}" for k in keys) + "}"


def _emit_fields(props: dict, ind: int, out: list):
    pad = "  " * ind
    for k, node in props.items():
        kk = _q(k)
        t = node.get("type")
        if t == "object":
            out.append(f"{pad}{kk}:")
            for a in ("type", "description", "nullable"):
                if a in node:
                    out.append(f"{pad}  {a}: {_q(node[a])}")
            out.append(f"{pad}  properties:")
            _emit_fields(node.get("properties") or {}, ind + 2, out)
        elif t == "array":
            out.append(f"{pad}{kk}:")
            for a in ("type", "description", "dedupe"):
                if a in node:
                    out.append(f"{pad}  {a}: {_q(node[a])}")
            it = node.get("items") or {"type": "string"}
            if it.get("type") == "object":
                out.append(f"{pad}  items:")
                out.append(f"{pad}    type: object")
                out.append(f"{pad}    properties:")
                _emit_fields(it.get("properties") or {}, ind + 3, out)
            else:
                out.append(f"{pad}  items: {_leaf(it)}")
        else:
            out.append(f"{pad}{kk}: {_leaf(node)}")


def to_yaml(spec: dict) -> str:
    out = [f"name: {spec['name']}", f"description: {_q(spec.get('description') or '')}"]
    cl = spec.get("classify") or {}
    out.append("classify:")
    out.append("  keywords:" + ("" if cl.get("keywords") else " {}"))
    for k, w in (cl.get("keywords") or {}).items():
        out.append(f"    {_q(str(k))}: {w}")
    out.append(f"  filename: {_q(cl.get('filename') or [])}")
    for k in ("pages", "few_shot", "page_images", "examples"):
        if spec.get(k) is not None:
            out.append(f"{k}: {_q(spec[k])}")
    ins = (spec.get("instructions") or "").rstrip()
    if ins:
        out.append("instructions: |")
        out += ["  " + ln if ln else "" for ln in ins.splitlines()]
    out.append("fields:")
    _emit_fields(spec.get("fields") or {}, 1, out)
    return "\n".join(out) + "\n"


def draft(name: str, title: str = "", description: str = "", template: str | None = None,
          rows: list | None = None) -> dict:
    name = (name or "").strip()
    if template and template.strip():
        fields = fields_from_template(template)
    else:
        fields = fields_from_table(rows or [])
    desc = (description or "").strip()
    if title and title.strip() and not desc.lower().startswith(title.strip().lower()):
        desc = f"{title.strip()}. {desc}".strip().rstrip(".") + "." if desc else title.strip()
    spec = {"name": name, "description": desc, "classify": suggest_classify(name, title or name, description),
            "pages": 3, "few_shot": 0, "instructions": DEFAULT_INSTRUCTIONS, "fields": fields}
    return spec


# ============================================================ validation
def _line_map(text: str) -> dict[str, int]:
    """dotted path ('fields.faktura.properties.numer') -> 1-based line, from the composed YAML node tree."""
    out: dict[str, int] = {}
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return out

    def walk(node, path):
        out.setdefault(path, node.start_mark.line + 1)
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                p = f"{path}.{k.value}" if path else str(k.value)
                out[p] = k.start_mark.line + 1
                walk(v, p)
        elif isinstance(node, yaml.SequenceNode):
            for i, v in enumerate(node.value):
                walk(v, f"{path}[{i}]")
    if root is not None:
        walk(root, "")
    return out


def _line(lines: dict, path: str) -> int | None:
    while path:
        if path in lines:
            return lines[path]
        path = path.rsplit(".", 1)[0] if "." in path else ""
    return None


def _check_fields(props, path: str, err, warn, depth=0):
    if not isinstance(props, dict) or not props:
        err(path, "Oczekiwano niepustej mapy pól (nazwa: definicja).")
        return
    for k, node in props.items():
        p = f"{path}.{k}"
        if not isinstance(node, dict):
            err(p, f"Pole '{k}': definicja musi być mapą, np. {{type: string}}.")
            continue
        t = node.get("type")
        if t not in TYPES:
            err(p, f"Pole '{k}': nieznany typ {t!r} (dozwolone: {', '.join(sorted(TYPES))}).")
            continue
        if t == "object":
            _check_fields(node.get("properties"), p + ".properties", err, warn, depth + 1)
        elif t == "array":
            it = node.get("items")
            if not isinstance(it, dict) or it.get("type") not in TYPES:
                err(p, f"Lista '{k}': brak poprawnego 'items' (np. items: {{type: string}} lub obiekt z properties).")
            elif it["type"] == "object":
                _check_fields(it.get("properties"), p + ".items.properties", err, warn, depth + 1)
            elif it["type"] == "array":
                err(p, f"Lista '{k}': lista list nie jest obsługiwana.")
            if node.get("dedupe") not in (None, "person"):
                err(p, f"Lista '{k}': dedupe może mieć tylko wartość 'person'.")
        elif t == "enum":
            vals = node.get("values")
            if not isinstance(vals, list) or not vals:
                err(p, f"Pole '{k}' (enum): wymagana niepusta lista 'values'.")
            else:
                for v in vals:
                    if isinstance(v, dict) and ("value" not in v or "label" not in v):
                        err(p, f"Pole '{k}': wartość enum jako mapa wymaga kluczy value i label.")
        norm = node.get("normalize")
        if norm is not None:
            names = [norm] if isinstance(norm, str) else norm
            if not isinstance(names, list):
                err(p, f"Pole '{k}': normalize musi być listą nazw.")
            else:
                for n in names:
                    if n not in NORMALIZERS:
                        err(p, f"Pole '{k}': nieznany normalizator {n!r} (dostępne: {', '.join(NORMALIZERS)}).")
        if "pattern" in node:
            try:
                re.compile(str(node["pattern"]))
            except re.error as e:
                err(p, f"Pole '{k}': błędne wyrażenie pattern: {e}.")
        d = node.get("derive")
        if d is not None:
            src = d.get("label_of") if isinstance(d, dict) else None
            if not src or src not in props or props[src].get("type") != "enum":
                err(p, f"Pole '{k}': derive.label_of musi wskazywać pole enum na tym samym poziomie.")
        if t in SCALARS and not node.get("description"):
            warn(p, f"Pole '{k}' nie ma opisu — opis trafia do promptu i poprawia trafność.")


def validate(text: str) -> dict:
    """Validate YAML text of a doctype exactly as the pipeline would load it. Returns
    {ok, errors: [{line, path, msg}], warnings: [...], name, spec (summary)}."""
    errors: list[dict] = []
    warnings: list[dict] = []
    try:
        d = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
        msg = " ".join(str(getattr(e, "problem", None) or e).split())
        return {"ok": False, "errors": [{"line": mark.line + 1 if mark else None, "path": "", "msg": f"Błąd składni YAML: {msg}"}],
                "warnings": []}
    lines = _line_map(text)

    def err(path, msg):
        errors.append({"line": _line(lines, path), "path": path, "msg": msg})

    def warn(path, msg):
        warnings.append({"line": _line(lines, path), "path": path, "msg": msg})

    if not isinstance(d, dict):
        return {"ok": False, "errors": [{"line": 1, "path": "", "msg": "Plik musi być mapą YAML (name:, description:, fields: …)."}],
                "warnings": []}
    name = d.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        err("name", "name: wymagane, małe litery/cyfry/_, zaczyna się literą, 2–41 znaków (np. faktura, przystapienie).")
    if not d.get("description"):
        err("description", "description: opisz typ dokumentu — opis trafia do klasyfikatora LLM i promptu ekstrakcji.")
    cl = d.get("classify") or {}
    if not isinstance(cl, dict):
        err("classify", "classify musi być mapą (keywords, filename).")
        cl = {}
    kws = cl.get("keywords") or {}
    if not isinstance(kws, dict):
        err("classify.keywords", "classify.keywords musi być mapą wzorzec: waga.")
        kws = {}
    for pat, w in kws.items():
        try:
            re.compile(str(pat))
        except re.error as e:
            err(f"classify.keywords.{pat}", f"Wzorzec {pat!r}: {e}.")
        if not isinstance(w, (int, float)):
            err(f"classify.keywords.{pat}", f"Waga wzorca {pat!r} musi być liczbą.")
    if not kws:
        warn("classify", "Brak słów kluczowych — typ będzie rozpoznawany wyłącznie przez LLM (z opisu).")
    if not isinstance(cl.get("filename", []), list):
        err("classify.filename", "classify.filename musi być listą fragmentów nazwy pliku.")
    for k in ("pages", "few_shot"):
        if d.get(k) is not None and (not isinstance(d[k], int) or d[k] < 0):
            err(k, f"{k} musi być nieujemną liczbą całkowitą.")
    if d.get("instructions") is not None and not isinstance(d["instructions"], str):
        err("instructions", "instructions musi być tekstem (najlepiej blok '|').")
    if "fields" not in d:
        err("fields", "Brak sekcji fields.")
    else:
        _check_fields(d.get("fields"), "fields", err, warn)
    out: dict = {"ok": False, "errors": errors, "warnings": warnings, "name": name if isinstance(name, str) else None}
    if errors:
        return out
    # load exactly like the pipeline does and exercise everything derived from the spec
    try:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / f"{name}.yaml").write_text(text, encoding="utf-8")
            spec = load_specs(Path(td))[name]
        schema = spec.json_schema()
        from .extract import postprocess
        skeleton = postprocess(spec, {})
        guide = spec.field_guide()
    except Exception as e:  # noqa: BLE001
        errors.append({"line": None, "path": "", "msg": f"Specyfikacji nie da się załadować: {e!r}"})
        return out
    if d.get("deterministic"):
        warnings.append({"line": _line(lines, "deterministic"), "path": "deterministic",
                         "msg": "Sekcja deterministic nie jest sprawdzana w kreatorze — przetestuj profilem Reguły."})
    out.update(ok=True, spec={"name": name, "description": spec.description, "fields": _count(spec.fields),
                              "keywords": len(kws), "json_schema": schema, "skeleton": skeleton, "preview": _preview(spec.fields),
                              "guide": guide})
    return out


def _preview(props: dict) -> dict:
    """Output skeleton with one example item in every list (the real skeleton has empty lists)."""
    def one(node):
        t = node["type"]
        if t == "object":
            return _preview(node["properties"])
        if t == "array":
            return [one(node["items"])]
        return None
    return {k: one(v) for k, v in props.items()}


def _count(props: dict) -> int:
    n = 0
    for node in props.values():
        if node["type"] == "object":
            n += _count(node["properties"])
        elif node["type"] == "array" and node["items"]["type"] == "object":
            n += _count(node["items"]["properties"])
        else:
            n += 1
    return n


def load_spec_text(text: str):
    """DocSpec from YAML text via o2j.spec.load_specs (no file left behind)."""
    d = yaml.safe_load(text)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / f"{d['name']}.yaml").write_text(text, encoding="utf-8")
        return load_specs(Path(td))[d["name"]]
