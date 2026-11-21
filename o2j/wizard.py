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


# ============================================================ inference from an example document (LLM + deterministic post-processing)
INFER_TYPES = ["string", "date", "integer", "number", "enum", "array_string"]
INFER_NORMS = ["none", *NORMALIZERS]
TYPE_ALIASES = {"text": "string", "str": "string", "tekst": "string", "int": "integer", "liczba": "integer",
                "float": "number", "decimal": "number", "amount": "number", "money": "number", "kwota": "number",
                "datetime": "date", "data": "date", "bool": "enum", "boolean": "enum", "list": "array_string",
                "array": "array_string", "lista": "array_string"}
MAX_INFER_FIELDS = 40
INFER_SYSTEM = """Projektujesz schemat ekstrakcji danych dla NOWEGO typu dokumentu na podstawie przykładu.
Zwróć JSON zgodny ze schematem. Zasady:
- name: krótka nazwa typu, snake_case, po polsku bez polskich znaków (np. przystapienie, odpowiedz_na_odwolanie).
- title: nazwa dokumentu tak, jak nazywa go nagłówek (np. "Przystąpienie do postępowania odwoławczego").
- description: 1–2 zdania, czym jest ten dokument; not_this: czym ten dokument NIE jest (podobne pisma, z którymi łatwo go pomylić).
- keywords: 3–8 fraz skopiowanych DOSŁOWNIE z dokumentu, typowych dla KAŻDEGO dokumentu tego typu (nagłówek, stałe formuły).
  Nigdy nazwy firm, osób, adresów, kwot, dat ani numerów. weight: 5 dla nagłówka/tytułu, 1–3 dla pozostałych.
- fields: 8–30 pól z danymi, które warto wyciągać z dokumentów tego typu (strony, daty, sygnatury, numery, kwoty, żądania…).
  path: sekcje i pola snake_case bez polskich znaków, rozdzielone kropką, np. "Pismo.data", "Przystepujacy.nip".
  Powtarzalne podmioty (lista osób/firm/zarzutów) oznacz "[]" przy sekcji: "Pelnomocnicy[].imie_nazwisko".
  type: string | date | integer | number (kwoty) | enum (zamknięty zbiór wartości, podaj values) | array_string (lista tekstów).
  normalize: nip | krs | regon | pesel | iban | bzp | ted | date | amount | person (imię i nazwisko) | city | integer | digits | strip | none.
  description: co wpisać i skąd to wziąć w dokumencie. example: wartość z przykładu albo "" gdy brak.
- instructions: 0–4 krótkie wskazówki dla modelu ekstrahującego, specyficzne dla tego typu dokumentu."""


def infer_schema() -> dict:
    """JSON Schema (strict structured output) for the LLM proposal; flat field list with paths avoids recursion."""
    s = {"type": "string"}
    field = {"type": "object", "additionalProperties": False,
             "required": ["path", "type", "description", "normalize", "values", "example"],
             "properties": {"path": s, "type": {"type": "string", "enum": INFER_TYPES}, "description": s,
                            "normalize": {"type": "string", "enum": INFER_NORMS},
                            "values": {"type": "array", "items": s}, "example": s}}
    kw = {"type": "object", "additionalProperties": False, "required": ["phrase", "weight"],
          "properties": {"phrase": s, "weight": {"type": "integer"}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["name", "title", "description", "not_this", "keywords", "instructions", "fields"],
            "properties": {"name": s, "title": s, "description": s, "not_this": s,
                           "keywords": {"type": "array", "items": kw},
                           "instructions": {"type": "array", "items": s},
                           "fields": {"type": "array", "items": field}}}


def sanitize_name(raw: str, title: str = "", taken: set[str] | frozenset = frozenset()) -> str:
    """snake_case doctype name matching NAME_RE, not colliding with built-in/existing types."""
    def snake(s: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", fold(s or "").lower()).strip("_")
        return re.sub(r"_+", "_", s)
    name = re.sub(r"^[^a-z]+", "", snake(raw))
    if len(name) > 30:  # long model names ("przystapienie_do_postepowania_odwolawczego") -> first words, no stop words
        keep: list[str] = []
        for w in [w for w in name.split("_") if w and w not in STOP]:
            if keep and len("_".join(keep + [w])) > 24:
                break
            keep.append(w)
        name = "_".join(keep)
    name = name[:41].strip("_")
    if not NAME_RE.match(name):
        words = [w for w in snake(title).split("_") if w and w not in STOP][:3]
        name = re.sub(r"^[^a-z]+", "", "_".join(words))[:41].strip("_")
    if not NAME_RE.match(name):
        name = "nowy_typ"
    base, i = name, 2
    while name in BUILTIN or name in taken:
        sfx = f"_{i}"
        name = base[:41 - len(sfx)] + sfx
        i += 1
    return name


def sanitize_key(raw: str) -> str:
    """Field / section key: ASCII letters, digits and _, never empty, never starting with a digit (case kept)."""
    k = re.sub(r"[^A-Za-z0-9_]+", "_", fold((raw or "").strip())).strip("_")
    k = re.sub(r"_+", "_", k)
    if not k:
        return ""
    return "f_" + k if k[0].isdigit() else k


def leaf_from_proposal(key: str, f: dict) -> dict:
    """Map an LLM field proposal to an allowed spec leaf: type in SCALARS (or list of texts), known normaliser."""
    t = str(f.get("type") or "string").strip().lower()
    t = TYPE_ALIASES.get(t, t)
    if t not in INFER_TYPES:
        t = "string"
    desc = " ".join(str(f.get("description") or "").split())
    if t == "array_string":
        node = {"type": "array", "items": {"type": "string"}}
        if desc:
            node = {"type": "array", "description": desc, "items": {"type": "string"}}
        return node
    if t == "enum":
        vals = list(dict.fromkeys(str(v).strip() for v in (f.get("values") or []) if str(v).strip()))
        if str(f.get("type") or "").lower() in ("bool", "boolean") and not vals:
            vals = ["tak", "nie"]
        if len(vals) < 2:
            t = "string"  # an enum without a closed set of values is just text
        else:
            node = {"type": "enum", "values": vals}
            if desc:
                node["description"] = desc
            return node
    norm = str(f.get("normalize") or "none").strip().lower()
    hint = suggest(key)
    node: dict[str, Any] = {"type": t}
    if norm in NORMALIZERS:
        node["normalize"] = [norm]
        # the normaliser decides the output type (a date normaliser returns ISO dates, amount a number …)
        forced = {"date": "date", "amount": "number", "integer": "integer", "pesel": "integer"}.get(norm)
        if forced:
            node["type"] = forced
        if hint.get("normalize") == [norm]:
            for k in ("pattern", "single_person"):
                if k in hint:
                    node[k] = hint[k]
        elif norm == "person":
            node["single_person"] = True
    elif hint:  # "none"/"auto"/unknown normaliser -> field-name heuristic
        st = hint.get("type", t)
        if st == t or t == "string":  # trust the field-name heuristic unless the model chose a different scalar
            node.update(hint)
    if node["type"] in ("integer", "number", "date") and node.get("pattern"):
        node.pop("pattern")
    if desc:
        node["description"] = desc
    return node


def fields_from_proposal(items: list[dict], limit: int = MAX_INFER_FIELDS) -> tuple[dict, list[str]]:
    """Flat [{path: 'Sekcja[].pole', ...}] -> nested spec fields (objects / arrays of objects)."""
    out: dict = {}
    warns: list[str] = []
    n = 0
    for f in items or []:
        parts = [p.strip() for p in str(f.get("path") or "").split(".") if p.strip()]
        if not parts:
            continue
        segs = []
        for p in parts:
            arr = p.endswith("[]")
            k = sanitize_key(p[:-2] if arr else p)
            if k:
                segs.append((k, arr))
        if not segs:
            continue
        if n >= limit:
            warns.append(f"Pominięto pola ponad limit {limit}.")
            break
        props = out
        ok = True
        for k, arr in segs[:-1]:
            node = props.get(k)
            if node is None:
                node = ({"type": "array", "items": {"type": "object", "properties": {}}} if arr
                        else {"type": "object", "properties": {}})
                props[k] = node
            if node["type"] == "object":
                props = node["properties"]
            elif node["type"] == "array" and node["items"].get("type") == "object":
                props = node["items"]["properties"]
            else:  # a leaf already sits where a group is needed: keep the leaf, drop this field
                ok = False
                break
        if not ok:
            continue
        key, arr = segs[-1]
        if key in props:
            continue  # duplicate path
        props[key] = leaf_from_proposal(key, f)
        n += 1
    _prune_empty(out)
    for k, node in out.items():  # person lists dedupe like the built-ins
        if node["type"] == "array" and node["items"].get("type") == "object" and PERSON_LIST.search(fold(k).lower()):
            node["dedupe"] = "person"
    return out, list(dict.fromkeys(warns))


def _prune_empty(props: dict):
    for k in list(props):
        node = props[k]
        inner = node.get("properties") if node["type"] == "object" else \
            node["items"].get("properties") if node["type"] == "array" and node["items"].get("type") == "object" else None
        if inner is not None:
            _prune_empty(inner)
            if not inner:
                del props[k]


def _words(phrase: str) -> list[str]:
    return re.findall(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", phrase or "")


def keyword_pattern(phrase: str, text: str) -> tuple[str, bool] | None:
    """Regex for a keyword phrase if it really occurs in `text` (whitespace-tolerant, case-insensitive).
    Returns (pattern, is_heading); headings (upper-case phrase at a line start) get a case-sensitive anchored regex."""
    from .classify import _despace
    words = _words(phrase)
    if not words or any(ch.isdigit() for ch in phrase) or sum(len(w) for w in words) < 5:
        return None
    if len(words) > 6:  # a whole sentence of one example is not a formula shared by the type
        return None
    lw = [w.lower() for w in words]
    if all(w in STOP or w.startswith(DOMAIN_COMMON) for w in lw):
        return None  # generic domain words are no class evidence
    text = _despace(text or "")
    body = r"\s+".join(re.escape(w) for w in lw)
    if not re.search(r"\b" + body + r"\b", text, flags=re.I | re.M):
        return None
    head = r"\s+".join(re.escape(w.upper()) for w in words)
    if re.search(r"^\s*" + head + r"\b", text, flags=re.M):
        return rf"^\s*(?-i:{head})\b", True
    return r"\b" + body + r"\b", False


def infer_keywords(proposals: list[dict], texts: list[str], title: str = "",
                   reference: list[str] | None = None, limit: int = 6) -> tuple[dict, list[str]]:
    """Keep only keywords that occur in every example; drop the ones that also fire on reference documents of
    other (built-in) types. Heading keywords weigh 5, the rest 1–3."""
    warns: list[str] = []
    cands = list(proposals or [])
    if title:
        cands.append({"phrase": title, "weight": 5})
    kw: dict[str, int] = {}
    cores: list[str] = []
    dropped = []
    for c in cands:
        phrase = str(c.get("phrase") or "").strip()
        got = [keyword_pattern(phrase, t) for t in texts] if texts else [None]
        if not got or any(g is None for g in got):
            continue
        pat, heading = got[0]
        if any(g[1] != heading for g in got):  # heading in one example, running text in another: use the loose form
            pat, heading = keyword_pattern(phrase, "\n" + phrase.lower())[0], False
        core = re.sub(r"\\[bs]|\^|\(\?-i:|\)|[+*]", "", pat).lower()
        if pat in kw or any(core in c or c in core for c in cores):
            continue  # same formula already kept (or a longer / shorter variant of it)
        if reference and any(re.search(pat, r, flags=re.M | re.I) for r in reference):
            dropped.append(phrase)
            continue
        try:
            w = int(c.get("weight") or 1)
        except (TypeError, ValueError):
            w = 1
        kw[pat] = 5 if heading else max(1, min(3, w))
        cores.append(core)
        if len(kw) >= limit:
            break
    if dropped:
        warns.append("Pominięto słowa kluczowe występujące też w innych typach: " + ", ".join(f"„{d}”" for d in dropped[:5]) + ".")
    return kw, warns


_REFERENCE: dict[str, list[tuple[str, str]]] = {}


def reference_texts(train_dir: str | Path | None, types=tuple(sorted(BUILTIN)), per_type: int = 8) -> list[tuple[str, str]]:
    """(doctype, text) of example documents of the built-in types (text layer only, cached)."""
    if not train_dir:
        return []
    key = str(train_dir)
    if key not in _REFERENCE:
        from .pdf import load
        out = []
        dirs = sorted(p for p in Path(train_dir).glob("przyklad_*") if p.is_dir())[:per_type]
        for d in dirs:
            for t in types:
                p = d / f"{t}.pdf"
                if p.is_file():
                    try:
                        out.append((t, load(p, ocr=None).text()[:6000]))
                    except Exception:  # noqa: BLE001
                        pass
        _REFERENCE[key] = out
    return _REFERENCE[key]


def check_classification(spec_classify: dict, name: str, texts: list[str], specs: dict,
                         reference: list[tuple[str, str]], min_score: float = 3) -> list[str]:
    """Warnings if the new type does not win on its own examples or would steal built-in documents."""
    from types import SimpleNamespace
    from .classify import rule_scores
    allspecs = {**{k: s for k, s in specs.items() if k != name}, name: SimpleNamespace(classify=spec_classify)}
    warns = []
    for i, t in enumerate(texts):
        sc = rule_scores(t[:6000], "", allspecs)
        mine = sc.get(name, 0)
        other = max([v for k, v in sc.items() if k != name] or [0])
        if mine < min_score or mine - other < 2:
            best = max(sc, key=sc.get)
            warns.append(f"Przykład {i + 1}: reguły nie wskazują pewnie nowego typu ({name}: wynik {mine:g}, "
                         f"{best if best != name else 'drugi'} {other:g}) — zdecyduje LLM z opisu.")
    stolen = 0
    for true, t in reference:
        sc = rule_scores(t, "", allspecs)
        if sc.get(name, 0) > 0 and sc[name] >= sc.get(true, 0):
            stolen += 1
    if stolen:
        warns.append(f"Nowy typ wygrywa regułami na {stolen} dokumentach typów wbudowanych — dopracuj słowa kluczowe.")
    return warns


def build_inferred_spec(proposal: dict, texts: list[str], *, taken=frozenset(), pages: int = 3,
                        reference: list[tuple[str, str]] | None = None, specs: dict | None = None,
                        min_score: float = 3) -> tuple[dict, list[str]]:
    """Deterministic post-processing of the LLM proposal into a spec dict (input of to_yaml)."""
    warns: list[str] = []
    title = " ".join(str(proposal.get("title") or "").split())
    if title.isupper():  # heading copied in capitals -> sentence case
        title = title[:1] + title[1:].lower()
    name = sanitize_name(str(proposal.get("name") or ""), title, taken)
    plain = sanitize_name(str(proposal.get("name") or ""), title)
    if plain != name:
        warns.append(f"Nazwa „{plain}” jest zajęta — użyto „{name}”.")
    desc = " ".join(str(proposal.get("description") or "").split())
    if title and not desc.lower().startswith(title.lower()):
        desc = f"{title}. {desc}".strip() if desc else title
    neg = " ".join(str(proposal.get("not_this") or "").split())
    if neg:
        desc = desc.rstrip(".") + ". " + (neg if neg.lower().startswith("nie jest") else "Nie jest nim: " + neg[0].lower() + neg[1:])
    desc = desc.strip().rstrip(".") + "." if desc else f"Dokument typu {name}."
    fields, fw = fields_from_proposal(proposal.get("fields") or [])
    warns += fw
    ref_texts = [t for _, t in (reference or [])]
    kw, kww = infer_keywords(proposal.get("keywords") or [], texts, title, ref_texts)
    warns += kww
    if not kw:
        warns.append("Brak słów kluczowych występujących w przykładzie — typ rozpozna LLM z opisu.")
    classify = {"keywords": kw, "filename": suggest_classify(name, title or name, "")["filename"]}
    ins = [" ".join(str(i).split()).lstrip("-• ").strip() for i in (proposal.get("instructions") or [])]
    # dates/amounts/IDs are normalised by code: model hints about formats or normalisation only contradict the defaults
    ins = [i for i in ins if i and not re.search(r"forma[tc]|normaliz", i, flags=re.I)][:2]
    instructions = DEFAULT_INSTRUCTIONS + "".join(f"- {i}\n" for i in ins)
    spec = {"name": name, "description": desc, "classify": classify, "pages": max(1, min(pages, 5)), "few_shot": 0,
            "instructions": instructions, "fields": fields}
    if specs is not None:
        warns += check_classification(classify, name, texts, specs, reference or [], min_score)
    return spec, warns


def infer(texts: list[str], llm, *, model: str | None = None, taken=frozenset(), pages: int = 3,
          reference: list[tuple[str, str]] | None = None, specs: dict | None = None, min_score: float = 3,
          max_chars: int = 12000) -> dict:
    """Example document text(s) -> LLM proposal (structured output) -> validated YAML spec.
    Returns {yaml, spec, validation, warnings, meta}."""
    if not texts or not any(t.strip() for t in texts):
        raise ValueError("Dokument nie zawiera czytelnego tekstu")
    parts = []
    for i, t in enumerate(texts):
        cap = max_chars if i == 0 else max_chars // 3
        parts.append(f"### PRZYKŁAD {i + 1}\n{t[:cap]}")
    user = "Przykładowe dokumenty nowego typu:\n\n" + "\n\n".join(parts)
    proposal, meta = llm.extract_json(INFER_SYSTEM, user, infer_schema(), name="doctype_proposal", model=model,
                                      temperature=0)
    spec, warns = build_inferred_spec(proposal, texts, taken=taken, pages=pages, reference=reference, specs=specs,
                                      min_score=min_score)
    if not spec["fields"]:
        raise ValueError("Model nie zaproponował żadnych pól — spróbuj innego przykładu albo zdefiniuj typ ręcznie.")
    text = to_yaml(spec)
    v = validate(text)
    return {"yaml": text, "spec": spec, "validation": v, "warnings": warns, "proposal": proposal,
            "meta": {k: meta.get(k) for k in ("model", "usage", "attempts")}}
