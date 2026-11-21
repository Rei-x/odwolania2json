"""Field-level voting over several extraction runs (different models and/or sampled runs).

Per leaf path the most common value wins (null counts as a vote); ties go to a value that is found
literally in the document text, then to the first run (primary model). List lengths follow the majority.
"""
from __future__ import annotations

import json
from collections import Counter

from . import extract as E


def _flat(x, path="", out=None):
    out = {} if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            _flat(v, f"{path}.{k}" if path else k, out)
    elif isinstance(x, list):
        out[path + "#len"] = len(x)
        for i, v in enumerate(x):
            _flat(v, f"{path}[{i}]", out)
    else:
        out[path] = x
    return out


def _key(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def vote(results: list[dict], doc=None) -> tuple[dict, dict]:
    if len(results) == 1:
        return results[0], {"runs": 1}
    flats = [_flat(r) for r in results]
    # 1) pick the run whose list shapes match the majority as the skeleton
    len_keys = sorted({k for f in flats for k in f if k.endswith("#len")})
    maj_len = {k: Counter(f.get(k, 0) for f in flats).most_common(1)[0][0] for k in len_keys}
    base_i = next((i for i, f in enumerate(flats) if all(f.get(k, 0) == v for k, v in maj_len.items())), 0)
    base = json.loads(json.dumps(results[base_i]))
    text = " ".join(" ".join(p.text.split()) for p in doc.pages).lower() if doc else ""
    decided, disagreements = 0, []
    for path in [k for k in _flat(base) if not k.endswith("#len")]:
        vals = [f.get(path) for f in flats]
        cnt = Counter(_key(v) for v in vals)
        top = cnt.most_common()
        best = top[0][0]
        if len(top) > 1 and top[0][1] == top[1][1]:  # tie -> prefer value present in the document
            tied = [k for k, c in top if c == top[0][1]]
            located = [k for k in tied if json.loads(k) is not None and str(json.loads(k)).lower() in text]
            best = located[0] if located else _key(vals[0]) if _key(vals[0]) in tied else tied[0]
        if len(cnt) > 1:
            disagreements.append({"field": path, "votes": {k: c for k, c in cnt.items()}, "chosen": json.loads(best)})
        _set(base, path, json.loads(best))
        decided += 1
    return base, {"runs": len(results), "skeleton_run": base_i, "fields": decided, "disagreements": disagreements}


def _set(obj, path, value):
    import re
    toks = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cur = obj
    for i, t in enumerate(toks):
        last = i == len(toks) - 1
        if t.startswith("["):
            k = int(t[1:-1])
            if not isinstance(cur, list) or k >= len(cur):
                return
            if last:
                cur[k] = value
                return
            cur = cur[k]
        else:
            if not isinstance(cur, dict) or t not in cur:
                return
            if last:
                cur[t] = value
                return
            cur = cur[t]
