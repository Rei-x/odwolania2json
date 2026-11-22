"""People lists anchored in the document text: item order and owner of nested people (deterministic, no LLM).

Options on a list field in config/doctypes/*.yaml:

- `order: document`: items follow the order of their first mention in the document. The organiser's reference JSON
  uses document order: every list of 2+ signers / attorneys in data/train, data/blind and data/skany_uzp is in
  first-mention order (signers as in "reprezentowana przez: A, B", attorneys as in "udziela pełnomocnictwa: A, B").
  Scans whose signature block shows the same people in another order (B's signature left of A's) made the model
  copy the signature-block order.
- `owner: mention`: for a people list inside a list of parties (podpisujacy inside mocodawca). A person mentioned
  right after one party's own data ("<nazwa>, KRS …, NIP …, reprezentowana przez: X") or under a
  "W imieniu <nazwa>:" heading belongs to that party. When the model lists the person under several parties
  (a consortium signing in one joint "Za Mocodawcę:" block), the copies under the other parties are dropped.

A list whose people cannot all be located in the text stays as the model returned it.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

MAX_GAP = 400  # max chars between a party's data and a person attributed to it
REP_CUE = re.compile(r"reprezent|w osob|dzialaj|w imieniu|w zastepstwie|umocowan|uprawnion")
HEAD_CUE = re.compile(r"\b(?:w imieniu|za|dla)\s*:?\s*$")  # "W imieniu <nazwa>:" heading of a signature block
GRANT = re.compile(r"udziel\w*\s+(?:\w+\s+)?pelnomocnictw|ustanawia|upowaznia|pelnomocnictwo\s+przyjmuj")
_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")


def fold(s: str) -> str:
    """Lowercase without Polish diacritics ('Łukasz Żak' -> 'lukasz zak')."""
    s = unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def doc_text(doc) -> str:
    return fold(" ".join("\n".join(p.text for p in doc.pages).split()))


def _tokens(name) -> list[str]:
    return _WORD.findall(fold(name)) if isinstance(name, str) else []


def _stem(w: str) -> str:
    return w[:max(3, len(w) - 2)]  # tolerates case endings: Hanna/Hannę, Sikora/Sikorę, Kowalski/Kowalskiego


def _person_re(name):
    t = _tokens(name)
    if not 2 <= len(t) <= 4 or min(len(t[0]), len(t[-1])) < 2:
        return None  # not a plain personal name (e.g. a law firm as attorney): never located
    f, last = re.escape(_stem(t[0])), re.escape(_stem(t[-1]))
    return re.compile(rf"\b{f}[a-z]*(?:\s+[a-z]+)?\s+{last}[a-z]*|\b{last}[a-z]*\s+{f}[a-z]*")


class _People:
    """Mentions of the people named in a result; a span goes to the closest name ('Jan' vs 'Janina Kowalska')."""

    def __init__(self, text: str, names: list[str]):
        self.text = text
        self.names = list(dict.fromkeys(n for n in names if _person_re(n)))
        self._cache: dict[str, list[tuple[int, int]]] = {}

    def spans(self, name) -> list[tuple[int, int]]:
        if name in self._cache:
            return self._cache[name]
        pat = _person_re(name)
        out = []
        if pat is not None:
            me = " ".join(_tokens(name))
            others = [" ".join(_tokens(n)) for n in self.names if fold(n) != fold(name)]
            for m in pat.finditer(self.text):
                s = m.group(0)
                if all(fuzz.token_sort_ratio(s, me) >= fuzz.token_sort_ratio(s, o) for o in others):
                    out.append((m.start(), m.end()))
        self._cache[name] = out
        return out


def _name_of(item):
    if isinstance(item, dict):
        return next((v for v in item.values() if isinstance(v, str) and v.strip()), None)
    return item if isinstance(item, str) else None


def _key(name) -> tuple:
    t = _tokens(name)
    return (t[0], t[-1]) if len(t) >= 2 else tuple(t)


def _person_names(props: dict, value) -> list[str]:
    """All names in the result's people lists (competitors when attributing a mention)."""
    out = []
    value = value if isinstance(value, dict) else {}
    for k, node in props.items():
        v = value.get(k)
        if node["type"] == "object":
            out += _person_names(node["properties"], v)
        elif node["type"] == "array" and isinstance(v, list):
            it = node["items"]
            for x in v:
                if it["type"] == "object":
                    if node.get("dedupe") == "person" or node.get("order") == "document":
                        n = _name_of(x)
                        if n:
                            out.append(n)
                    out += _person_names(it["properties"], x)
    return out


def _ordered(items: list, people: _People) -> list | None:
    first = []
    for it in items:
        sp = people.spans(_name_of(it))
        if not sp:
            return None
        first.append(sp[0][0])
    if len(set(first)) < len(first):
        return None
    return [it for _, it in sorted(zip(first, items), key=lambda x: x[0])]


def _anchors(text: str, digits: str, idx: list[int], item: dict, skip: str) -> list[tuple[int, int, bool]]:
    """Where a party's own data (name, KRS, NIP …) occurs: (start, end, is_name)."""
    vals: list = []

    def walk(x, top=True):
        if isinstance(x, dict):
            for k, v in x.items():
                if not (top and k == skip):
                    walk(v, False)
        elif isinstance(x, (str, int)) and not isinstance(x, bool):
            vals.append(str(x))
    walk(item)
    out = []
    for s in vals:
        d = re.sub(r"\D", "", s)
        if len(d) >= 9 and len(d) >= len(re.sub(r"[\s-]", "", s)) - 2:  # identifier (KRS / NIP / REGON)
            for m in re.finditer(re.escape(d), digits):
                a, b = idx[m.start()], idx[m.end() - 1] + 1
                if b - a <= len(d) + 6:  # digits of one number, not of several neighbouring ones
                    out.append((a, b, False))
        else:
            f = " ".join(fold(s).split())
            if len(f) >= 6:
                out += [(m.start(), m.end(), True) for m in re.finditer(re.escape(f), text)]
    return out


def _owners(spans, anchors, text: str) -> set[int]:
    owners = set()
    for s, _ in spans:
        prev = [a for a in anchors if a[1] <= s]
        if not prev:
            continue
        a, b, is_name, party = max(prev, key=lambda x: x[1])
        gap = text[b:s]
        if len(gap) > MAX_GAP or GRANT.search(gap):
            continue
        if REP_CUE.search(gap) or (is_name and HEAD_CUE.search(text[max(0, a - 15):a])):
            owners.add(party)
    return owners


def _assign_owners(path: str, parties: list, key: str, text: str, people: _People, changes: list):
    digits_idx = [i for i, c in enumerate(text) if c.isdigit()]
    digits = "".join(text[i] for i in digits_idx)
    anchors = []
    for j, party in enumerate(parties):
        anchors += [(a, b, nm, j) for a, b, nm in _anchors(text, digits, digits_idx, party, key)]
    lists = [p.get(key) if isinstance(p.get(key), list) else [] for p in parties]
    keys = [{_key(_name_of(x)) for x in lst} for lst in lists]
    for i, lst in enumerate(lists):
        keep = []
        for x in lst:
            own = _owners(people.spans(_name_of(x)), anchors, text)
            if own and i not in own and any(_key(_name_of(x)) in keys[j] for j in own):
                changes.append({"field": f"{path}[{i}].{key}", "action": "drop", "value": _name_of(x),
                                "owner": f"{path}[{min(own)}]"})
                continue
            keep.append(x)
        if len(keep) != len(lst):
            parties[i][key] = keep


def _walk(props: dict, value, path: str, text: str, people: _People, changes: list):
    if not isinstance(value, dict):
        return
    for k, node in props.items():
        v = value.get(k)
        p = f"{path}.{k}" if path else k
        if node["type"] == "object":
            _walk(node["properties"], v, p, text, people, changes)
        elif node["type"] == "array" and isinstance(v, list) and node["items"]["type"] == "object":
            sub = node["items"]["properties"]
            if len(v) >= 2 and all(isinstance(x, dict) for x in v):
                for ck, cn in sub.items():
                    if cn["type"] == "array" and cn.get("owner") == "mention":
                        _assign_owners(p, v, ck, text, people, changes)
            for i, x in enumerate(v):
                _walk(sub, x, f"{p}[{i}]", text, people, changes)
            if node.get("order") == "document" and len(v) >= 2:
                new = _ordered(v, people)
                if new is not None and new != v:
                    changes.append({"field": p, "action": "order", "before": [_name_of(x) for x in v],
                                    "after": [_name_of(x) for x in new]})
                    v[:] = new


def apply(spec, result: dict, doc) -> list[dict]:
    """Reorders / reassigns people lists of `result` in place; returns the changes (for the trace)."""
    if not isinstance(result, dict) or not doc.pages:
        return []
    text = doc_text(doc)
    if not text.strip():
        return []
    changes: list[dict] = []
    people = _People(text, _person_names(spec.fields, result))
    _walk(spec.fields, result, "", text, people, changes)
    return changes
