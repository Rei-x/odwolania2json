"""Deterministic (no-LLM) extraction driven by the optional `deterministic:` section of a doctype YAML.

The code holds only generic text primitives (scopes, regexes, label anchors, list splitting, keyword maps);
everything document-specific (which anchors, which patterns, which enum keywords) lives in YAML, so a new
document class is configured without code changes. The raw result goes through the same
`extract.postprocess` normalisers as LLM output, so formats are identical.

YAML outline (all keys optional unless stated):

  deterministic:
    pages: 4                      # leading pages to read (default: spec.pages)
    drop_lines: ['^Strona \\d+ z \\d+$']   # noise lines removed before matching (page footers ...)
    defs: {date: '...', name: '...'}       # regex snippets, referenced as {date} in any pattern
    classify: {keywords: {...}, min_score: 5, min_margin: 2}   # extra rule weights for this mode
    scopes:                       # named text regions, always resolved on the whole document
      header: {to: ['^ODWOŁANIE'], pages: [1]}
      odw:    {from: '^Odwołujący\\s*:', to: ['^Zamawiający', '^dotyczy'], within: header, last: false}
    fields:                       # mirrors the `fields:` tree of the spec
      Obj:
        field: <rule> | [<rule>, <rule>, ...]      # alternatives, first non-empty wins
      List:                                        # array of objects
        scope: odw                                 # region holding the items
        split: '^\\d\\)\\s*Lider[^\\n]*\\n'        # item blocks start at each match (none -> one block); list = fallbacks
        findall: '<regex with named groups>'       # one item per match (on the selected blocks), see _findall
        pick: index                                # nested list: n-th block for the n-th parent item
        limit: 1
        prefer_header: 'Lider'                     # move blocks whose split line matches to the front
        item: {field: <rule>, ...}                 # rules evaluated on the item block
        index_values: {field: [1, 0]}              # by item position (last value repeats) unless a rule set it
        single_null: [field]                       # set these fields to null when only one item

  <rule> keys:
    scope: name | {from:, to:, ...}   # region to search (named: global; inline: inside current block)
    regex: str | [str]            # value = group 'v' (else group 1, else whole match); `group: name` overrides
    near: {label: re, value: re, window: 200}  # first `value` match within `window` chars after `label`
    label: re                     # rest of the line after the label, or the next non-empty line
    lines: N, until: re           # with label: append up to N continuation lines, stopping at `until`
    first_line: true              # first non-empty line of the scope / block
    map: [[re, value], ...]       # first pattern that matches the scope text gives the value
    pick: earliest                # with map: the pattern matching earliest in the text wins instead
    present: re, then: 1, else: 0 # flag
    const: value
    from_field: sibling           # apply the rule to an already extracted sibling value instead of text
    when: {field: sibling, equals: value}     # rule applies only if the sibling has that value
    flat: true                    # match on whitespace-collapsed text (patterns may then span lines)
    nth: 2                        # take the n-th match (1-based)
    cut: re | [re]                # truncate the value at the first match
    sub: [[re, repl], ...]        # regex substitutions on the value
    strip: ' ,.;:„”"'            # characters stripped from both ends
    exclude: re                   # discard value if it matches
    year_from: sibling            # date without a year ('16 lutego br.') gets the year of a sibling date
    nominative: true              # Polish name de-declension ('Klaudię Nowak' -> 'Klaudia Nowak')
    date_words: true              # 'dwunastego stycznia 2026' -> '12 stycznia 2026'
  defs: built-in {day_words} = Polish ordinal day words (pierwszego ... trzydziestego pierwszego)
    scope: _header                # the split line that opened the current list item (e.g. '1) Zamawiający - Lider:')
  scope keys: from, to, within, pages, last, include_from, max_chars,
              first_of: [scope, ...] (first existing), column: {header, split, index} (two-column tables)
"""
from __future__ import annotations

import re
from typing import Any

from .spec import DocSpec

_FLAGS = re.M


def _as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _flat(s: str) -> str:
    return " ".join(s.split())


class _Ctx:
    def __init__(self, spec: DocSpec, pages: list[str]):
        self.cfg = spec.raw.get("deterministic") or {}
        self.defs = {"day_words": DAY_WORDS + r"(?:\s+(?:" + "|".join(_UNITS) + "))?",
                     **{k: str(v) for k, v in (self.cfg.get("defs") or {}).items()}}
        drops = [re.compile(self.p(d)) for d in _as_list(self.cfg.get("drop_lines"))]
        self.pages = ["\n".join(ln for ln in p.split("\n") if not any(d.search(ln.strip()) for d in drops))
                      for p in pages]
        self.text = "\n".join(self.pages)
        self.scope_cfg = self.cfg.get("scopes") or {}
        self._scopes: dict[str, str | None] = {}
        self.header = ""
        self.parent_count = 1

    # ---- patterns
    def p(self, pattern: str) -> str:
        """Expand {name} references to defs (repeatedly, so defs may reference defs)."""
        prev = None
        while prev != pattern:
            prev = pattern
            pattern = re.sub(r"\{([a-z_][a-z0-9_]*)\}", lambda m: f"(?:{self.defs[m.group(1)]})"
                             if m.group(1) in self.defs else m.group(0), pattern)
        return pattern

    def rx(self, pattern: str) -> re.Pattern:
        return re.compile(self.p(pattern), _FLAGS)

    # ---- scopes
    def scope(self, ref, base: str) -> str | None:
        if ref is None:
            return base
        if ref == "_header":  # the split line that opened the current list item
            return self.header
        if isinstance(ref, str):
            if ref not in self._scopes:
                cfg = self.scope_cfg.get(ref)
                self._scopes[ref] = None if cfg is None else self._region(cfg, None)
            return self._scopes[ref]
        return self._region(ref, base)

    def _region(self, cfg: dict, base: str | None) -> str | None:
        if "first_of" in cfg:  # alternatives: the first scope that exists
            for ref in _as_list(cfg["first_of"]):
                r = self.scope(ref, base if base is not None else self.text)
                if r is not None and r.strip():
                    return r
            return None
        if "column" in cfg:
            return self._column(cfg["column"])
        if "within" in cfg:
            base = self.scope(cfg["within"], self.text)
        elif "pages" in cfg:
            base = "\n".join(self.pages[i - 1] for i in cfg["pages"] if 0 < i <= len(self.pages))
        elif base is None:
            base = self.text
        if base is None:
            return None
        start = 0
        if cfg.get("from"):
            hits = []
            for pat in _as_list(cfg["from"]):
                ms = list(self.rx(pat).finditer(base))
                if ms:
                    hits.append(ms[-1] if cfg.get("last") else ms[0])
            if not hits:
                return None
            m = (max if cfg.get("last") else min)(hits, key=lambda m: m.start())
            start = m.start() if cfg.get("include_from") else m.end()
        end = len(base)
        for pat in _as_list(cfg.get("to")):
            m = self.rx(pat).search(base, start + (1 if cfg.get("include_from") else 0))
            if m and m.start() < end:
                end = m.start()
        if cfg.get("max_chars"):
            end = min(end, start + int(cfg["max_chars"]))
        return base[start:end]


    def _column(self, c: dict) -> str | None:
        """Two-column table flattened by text extraction ('Odwołujący Zamawiający' / 'A sp. j. B S.A.' / ...):
        lines after the `header` line are cut in two at the first `split` match (or before the repeated
        leading label, e.g. 'KRS: 1 KRS: 2'); returns column `index` (0/1) until a line that cannot be cut."""
        m = self.rx(c["header"]).search(self.text)
        if not m:
            return None
        split = self.rx(c["split"]) if c.get("split") else None
        out = []
        for ln in self.text[m.end():].split("\n"):
            ln = ln.strip()
            if not ln:
                continue
            parts = None
            lab = re.match(r"([A-ZŁŚŻŹĆ][\w.]*:?)\s", ln)
            if lab:
                k = ln.find(" " + lab.group(1) + " ", 1)
                if k > 0:
                    parts = [ln[:k], ln[k + 1:]]
            if parts is None and split:
                sm = split.search(ln)
                if sm and 0 < sm.start() < len(ln):
                    parts = [ln[: sm.start()], ln[sm.end():]]
            if parts is None:
                break
            out.append(parts[int(c.get("index", 0))].strip())
        return "\n".join(out) if out else None


# ---------------------------------------------------------------- rules
def _group(m: re.Match) -> str:
    gd = m.groupdict()
    if "v" in gd:
        return m.group("v")
    return m.group(1) if m.re.groups else m.group(0)


def _post(ctx: _Ctx, rule: dict, v):
    if v is None or not isinstance(v, str):
        return v
    v = " ".join(v.split())
    for pat in _as_list(rule.get("cut")):
        m = ctx.rx(pat).search(v)
        if m:
            v = v[: m.start()]
    for pat, repl in rule.get("sub") or []:
        v = ctx.rx(pat).sub(repl, v)
    v = v.strip(rule.get("strip", " ,;:"))
    if rule.get("exclude") and ctx.rx(rule["exclude"]).search(v):
        return None
    return v or None


def _apply_rule(ctx: _Ctx, rule, base: str, siblings: dict):
    v = _apply_rule_inner(ctx, rule, base, siblings)
    if not isinstance(rule, dict) or not isinstance(v, str):
        return v
    if rule.get("year_from") and not re.search(r"\d{4}", v):  # '16 lutego br.' -> year of a sibling date
        y = re.search(r"\d{4}", str(siblings.get(rule["year_from"]) or ""))
        if not y:
            return None
        v = re.sub(r"\s*\b(?:br|b\.r)\.?$", "", v) + " " + y.group(0)
    if rule.get("nominative"):
        v = nominative(v)
    if rule.get("date_words"):
        v = date_words(v)
    return v


_UNITS = {"pierwszego": 1, "drugiego": 2, "trzeciego": 3, "czwartego": 4, "piątego": 5, "szóstego": 6,
          "siódmego": 7, "ósmego": 8, "dziewiątego": 9}
_TEENS = {"dziesiątego": 10, "jedenastego": 11, "dwunastego": 12, "trzynastego": 13, "czternastego": 14,
          "piętnastego": 15, "szesnastego": 16, "siedemnastego": 17, "osiemnastego": 18, "dziewiętnastego": 19}
_TENS = {"dwudziestego": 20, "trzydziestego": 30}
DAY_WORDS = "|".join(sorted(list(_UNITS) + list(_TEENS) + list(_TENS), key=len, reverse=True))


def date_words(v: str) -> str:
    """'dwudziestego pierwszego stycznia 2026' -> '21 stycznia 2026' (Polish ordinal day words)."""
    def rep(m):
        a, b = m.group(1).lower(), (m.group(2) or "").lower()
        n = _TENS.get(a, 0) + _UNITS.get(b, 0) if a in _TENS else _TEENS.get(a, _UNITS.get(a, 0))
        return str(n) if n else m.group(0)
    return re.sub(rf"\b({DAY_WORDS})(?:\s+({'|'.join(_UNITS)}))?\b", rep, v, flags=re.I)


_TITLE_PREFIX = re.compile(r"^(?:Pan[aui]?|Pani[aą]?)\s+")


def _nom_token(t: str, masc_decl: bool, first: bool = False) -> str:
    low = t.lower()
    for suf, rep in (("skiego", "ski"), ("ckiego", "cki"), ("dzkiego", "dzki"), ("skiemu", "ski"), ("ckiemu", "cki"),
                     ("dzkiemu", "dzki"), ("skiej", "ska"), ("ckiej", "cka"), ("dzkiej", "dzka")):
        if low.endswith(suf):
            return t[: len(t) - len(suf)] + rep
    if low.endswith(("ę", "ą")) and len(t) >= 3:
        return t[:-1] + "a"
    if low.endswith(("ii", "ji")) and len(t) > 4:  # Marii, Patrycji
        return t[:-1] + "a"
    if first and not masc_decl and len(t) > 4:  # female first-name dative: Iwonie, Elżbiecie, Barbarze, Oldze, Monice
        for suf, rep in (("cie", "ta"), ("dzie", "da"), ("rze", "ra"), ("dze", "ga"), ("ce", "ka")):
            if low.endswith(suf) and not low.endswith("owie"):
                return t[: len(t) - len(suf)] + rep
        if low.endswith("ie") and low[-3] in "nlwmbpfsz" and not low.endswith("owie"):
            return t[:-2] + "a"
    if low.endswith(("remu", "rzemu", "niemu")) and len(t) > 5:  # Cezaremu, Jerzemu, Antoniemu
        return t[:-3] + "y" if not low.endswith("niemu") else t[:-3] + "i"
    stem = None
    if low.endswith("owi") and len(t) > 5:
        stem = t[:-3]
    elif masc_decl and low.endswith("a") and len(t) > 3:
        stem = t[:-1]
    if stem is None:
        return t
    for a, b in (("wł", "weł"), ("rk", "rek"), ("ck", "cek"), ("tk", "tek"), ("łk", "łek")):  # fleeting e: Pawła -> Paweł
        if stem.lower().endswith(a):
            return stem[: len(stem) - len(a)] + b
    return stem


def nominative(name: str) -> str:
    """Best-effort Polish personal-name de-declension (dative/accusative/genitive -> nominative) for text like
    'udzielam pełnomocnictwa Klaudii Szymańskiej' / 'reprezentowany przez Jana Kowalskiego'. Only unambiguous
    case endings are touched, so names already in the nominative pass through unchanged."""
    name = _TITLE_PREFIX.sub("", name.strip())
    toks = name.split()
    masc = any(t.lower().endswith(("ego", "emu", "owi")) for t in toks)
    return " ".join(_nom_token(t, masc, i == 0) for i, t in enumerate(toks))


def _apply_rule_inner(ctx: _Ctx, rule, base: str, siblings: dict):
    if not isinstance(rule, dict):
        return rule  # literal value
    if "when" in rule:
        w = rule["when"]
        if siblings.get(w["field"]) != w.get("equals"):
            return None
    if "const" in rule:
        return rule["const"]
    if "from_field" in rule:
        text = siblings.get(rule["from_field"])
        if not isinstance(text, str):
            return None
    else:
        text = ctx.scope(rule.get("scope"), base)
    if text is None:
        return rule.get("else") if "present" in rule else None
    if rule.get("flat"):
        text = _flat(text)
    nth = int(rule.get("nth", 1))

    if "present" in rule:
        hit = any(ctx.rx(p).search(text) for p in _as_list(rule["present"]))
        return rule.get("then", 1) if hit else rule.get("else")
    if "map" in rule:
        if rule.get("pick") == "earliest":  # pattern matching earliest in the text wins (ties: list order)
            best = None
            for i, (pat, val) in enumerate(rule["map"]):
                m = ctx.rx(pat).search(text)
                if m and (best is None or m.start() < best[0]):
                    best = (m.start(), val)
            return best[1] if best else None
        for pat, val in rule["map"]:
            if ctx.rx(pat).search(text):
                return val
        return None
    if rule.get("first_line"):
        for ln in text.split("\n"):
            if ln.strip():
                return _post(ctx, rule, ln)
        return None
    if "near" in rule:
        n = rule["near"]
        vrx = ctx.rx(n["value"])
        win = int(n.get("window", 200))
        found = []
        for lab in _as_list(n["label"]):
            for m in ctx.rx(lab).finditer(text):
                vm = vrx.search(text, m.end())
                if vm and vm.start() <= m.end() + win:
                    found.append((m.start(), _group(vm)))
                    break
            if found and not n.get("any_label_order"):
                break  # labels are listed by priority
        if len(found) >= 1:
            return _post(ctx, rule, found[0][1])
        return None
    if "label" in rule:
        for lab in _as_list(rule["label"]):
            m = ctx.rx(lab).search(text)
            if not m:
                continue
            rest = text[m.end():]
            lines = rest.split("\n")
            first = lines[0].strip(" :\t")
            out, i = [], 1
            if first:
                out.append(first)
            else:
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines):
                    out.append(lines[i].strip())
                    i += 1
            until = ctx.rx(rule["until"]) if rule.get("until") else None
            for ln in lines[i: i + int(rule.get("lines", 0))]:
                if not ln.strip() or (until and until.search(ln.strip())):
                    break
                out.append(ln.strip())
            v = _post(ctx, rule, " ".join(out))
            if v:
                return v
        return None
    if "regex" in rule:
        for pat in _as_list(rule["regex"]):
            ms = list(ctx.rx(pat).finditer(text))
            if len(ms) >= abs(nth):
                m = ms[nth - 1 if nth > 0 else nth]
                v = _post(ctx, rule, m.group(rule["group"]) if rule.get("group") else _group(m))
                if v:
                    return v
        return None
    return None


def _rules(ctx: _Ctx, rules, base: str, siblings: dict):
    for r in _as_list(rules) if isinstance(rules, list) else [rules]:
        v = _apply_rule(ctx, r, base, siblings)
        if v not in (None, "", []):
            return v
    return None


# ---------------------------------------------------------------- tree walk
def _object(ctx: _Ctx, props: dict, cfg: dict, base: str, index: int = 0) -> dict:
    out: dict[str, Any] = {}

    def dependent(c) -> bool:  # rules reading sibling values run after the independent ones
        return any(isinstance(r, dict) and ("when" in r or "from_field" in r or "year_from" in r)
                   for r in (c if isinstance(c, list) else [c]))
    order = sorted(props, key=lambda k: dependent((cfg or {}).get(k)))
    for k in order:
        node = props[k]
        c = (cfg or {}).get(k)
        if c is None:
            continue
        t = node["type"]
        if t == "object":
            out[k] = _object(ctx, node["properties"], c if isinstance(c, dict) else {}, base, index)
        elif t == "array":
            out[k] = _array(ctx, node["items"], c, base, index)
        else:
            out[k] = _rules(ctx, c, base, out)
    return {k: out[k] for k in props if k in out}


def _blocks(ctx: _Ctx, cfg: dict, text: str) -> list[tuple[str, str]]:
    """Item blocks as (header, body): header = the split match, body = text up to the next match."""
    if not cfg.get("split"):
        return [("", text)]
    ms = []
    for pat in _as_list(cfg["split"]):  # alternatives: the first pattern that matches at all is used
        ms = list(ctx.rx(pat).finditer(text))
        if ms:
            break
    if not ms:
        return [("", text)] if cfg.get("keep_unsplit", True) else []
    return [(m.group(0), text[m.end(): (ms[i + 1].start() if i + 1 < len(ms) else len(text))]) for i, m in enumerate(ms)]


def _person_key(v) -> tuple:
    toks = str(v or "").lower().split()
    return (toks[0], toks[-1]) if len(toks) >= 2 else tuple(toks)


def _findall(ctx: _Ctx, item_node: dict, cfg: dict, text: str) -> list:
    """One item per regex match (named groups = item fields), in document order. Options:
    split_group: {group: g, by: re, field: f}  -> a matched list ('A, B oraz C') becomes several items
    merge_on: field                           -> items with the same person (first+last token) are merged"""
    src = _flat(text) if cfg.get("flat") else text
    hits = []
    for pat in _as_list(cfg["findall"]):
        for m in ctx.rx(pat).finditer(src):
            gd = {k: " ".join(v.split()) for k, v in m.groupdict().items() if v is not None}
            sg = cfg.get("split_group")
            if sg and sg["group"] in gd:
                parts = [x for x in ctx.rx(sg["by"]).split(gd.pop(sg["group"])) if x and x.strip()]
                for j, part in enumerate(parts):
                    hits.append((m.start() + j / 100, {**gd, sg["field"]: part.strip()}))
            else:
                hits.append((m.start(), gd))
    hits.sort(key=lambda x: x[0])
    excl = ctx.rx(cfg["exclude"]) if cfg.get("exclude") else None
    items: list = []
    seen: dict = {}
    for _, gd in hits:
        if excl and any(excl.search(v) for v in gd.values()):
            continue
        if item_node["type"] != "object":
            items.append(next(iter(gd.values()), None))
            continue
        it = {k: gd.get(k) for k in item_node["properties"]}
        for k, r in (cfg.get("item") or {}).items():
            v = _rules(ctx, r, " ".join(gd.values()), it)
            if v is not None:
                it[k] = v
        mk = cfg.get("merge_on")
        if mk and it.get(mk):
            key = _person_key(it[mk])
            if key in seen:
                prev = seen[key]
                for k, v in it.items():
                    if prev.get(k) is None and v is not None:
                        prev[k] = v
                continue
            seen[key] = it
        items.append(it)
    return items


def _array(ctx: _Ctx, item_node: dict, cfg, base: str, parent_index: int) -> list:
    if not isinstance(cfg, dict):
        return []
    text = ctx.scope(cfg.get("scope"), base)
    if text is None:
        return []
    items: list = []
    blocks = _blocks(ctx, cfg, text)
    if cfg.get("prefer_header"):  # e.g. consortium: the Leader block first, wherever it is listed
        prx = ctx.rx(cfg["prefer_header"])
        blocks.sort(key=lambda hb: 0 if prx.search(hb[0]) else 1)
    if cfg.get("pick") == "index":  # n-th block belongs to the n-th parent item (e.g. signatures per principal)
        if ctx.parent_count <= 1:
            blocks = [("", "\n".join(h + b for h, b in blocks))]
        elif len(blocks) > 1 or parent_index == 0:
            blocks = blocks[parent_index: parent_index + 1]
        else:
            blocks = []
    if cfg.get("findall"):
        items = _findall(ctx, item_node, cfg, "\n".join(h + b for h, b in blocks))
    else:
        for i, (h, b) in enumerate(blocks):
            saved, ctx.header = ctx.header, h
            saved_n, ctx.parent_count = ctx.parent_count, len(blocks)
            if item_node["type"] == "object":
                items.append(_object(ctx, item_node["properties"], cfg.get("item") or {}, b, i))
            else:
                items.append(_rules(ctx, cfg.get("item"), b, {}))
            ctx.header, ctx.parent_count = saved, saved_n
    if cfg.get("limit"):
        items = items[: int(cfg["limit"])]
    for k, vals in (cfg.get("index_values") or {}).items():  # e.g. leader flag: first item 1, others 0
        for i, it in enumerate(items):
            if isinstance(it, dict) and it.get(k) is None and vals:
                it[k] = vals[min(i, len(vals) - 1)]
    if len(items) == 1:
        for k in cfg.get("single_null") or []:
            if isinstance(items[0], dict):
                items[0][k] = None
    return items


# ---------------------------------------------------------------- public API
def has_rules(spec: DocSpec) -> bool:
    return bool((spec.raw.get("deterministic") or {}).get("fields"))


def pages_to_read(spec: DocSpec) -> int | None:
    return (spec.raw.get("deterministic") or {}).get("pages", spec.pages)


def extract(spec: DocSpec, page_texts: list[str]) -> dict:
    """Raw (pre-normalisation) result for one document; feed to extract.postprocess."""
    ctx = _Ctx(spec, page_texts)
    return _object(ctx, spec.fields, ctx.cfg.get("fields") or {}, ctx.text)


def classify(text: str, filename: str, specs: dict[str, DocSpec], min_score: float = 3,
             min_margin: float = 2) -> tuple[str, dict]:
    """Rules only (no LLM): base `classify.keywords` + filename hint (classify.rule_scores) plus the optional
    mode-specific `deterministic.classify.keywords` (e.g. negative weights for look-alike documents).
    A class is returned only when confident (score >= its min_score and margin >= min_margin); else 'inny'."""
    from .classify import _despace, rule_scores
    head = text[:6000]
    scores = rule_scores(head, filename, specs)
    t = _despace(head)
    for name, spec in specs.items():
        kw = ((spec.raw.get("deterministic") or {}).get("classify") or {}).get("keywords") or {}
        for pattern, w in kw.items():
            if re.search(pattern, t, flags=re.M | re.I):
                scores[name] = scores.get(name, 0.0) + float(w)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0.0
    dc = (specs[best].raw.get("deterministic") or {}).get("classify") or {}
    need = float(dc.get("min_score", min_score))
    margin = float(dc.get("min_margin", min_margin))
    confident = best_s >= need and best_s - second_s >= margin
    info = {"method": "rules", "scores": scores, "confident": confident}
    return (best if confident else "inny"), info
