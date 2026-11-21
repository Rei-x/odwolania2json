"""F1 scorer mirroring the organizer's description (Discord, UZP | MateuszSz):

TP - value present in prediction and matches ground truth (long strings: >=80% similarity)
TN - value absent in both
FP - value only in prediction, or present in both but wrong
FN - value absent in prediction but present in ground truth

Usage: python -m eval.score <pred_dir> <gt_dir> [--verbose]
Both dirs contain case subfolders with <name>.json files matched by relative path.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 80.0
# Organiser (Discord 12:26): long-string fields compared with 80% similarity; everything else exact.
FUZZY_FIELDS = {
    "Odwolujacy[].pelnomocnik.nazwa",   # nazwa firmy pełnomocnika
    "przelew_bankowy.tytul",            # tytuł przelewu
    "Odwolujacy[].nazwa", "Zamawiajacy[].nazwa",
    "ZamowieniePubliczne.tytul",        # tytuł zamówienia publicznego
}


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def _norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = " ".join(v.split())
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return s
    return v


def leaf_equal(p, g, path: str = "") -> bool:
    # numbers compare numerically only when both are JSON numbers; identifiers (KRS, NIP, accounts…) are strings
    # and must match exactly (leading zeros matter)
    if isinstance(p, (int, float)) or isinstance(g, (int, float)):
        pn, gn = _norm(p), _norm(g)  # a JSON number on either side -> numeric comparison ("200,00" == 200.0)
        if isinstance(pn, float) and isinstance(gn, float):
            return abs(pn - gn) < 0.005
    p, g = " ".join(str(p).split()), " ".join(str(g).split())
    if p == g:
        return True
    if _field_key(path) in FUZZY_FIELDS:
        return fuzz.ratio(p, g) >= FUZZY_THRESHOLD
    return False


def _flat_str(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _align(pred: list, gt: list) -> list[tuple]:
    """Greedy pairing of list items by similarity; unmatched items pair with None."""
    pairs, used = [], set()
    for g in gt:
        best, best_s = None, -1.0
        for i, p in enumerate(pred):
            if i in used:
                continue
            s = fuzz.ratio(_flat_str(p), _flat_str(g))
            if s > best_s:
                best, best_s = i, s
        if best is not None:
            used.add(best)
            pairs.append((pred[best], g))
        else:
            pairs.append((None, g))
    pairs += [(p, None) for i, p in enumerate(pred) if i not in used]
    return pairs


def compare(pred, gt, path: str, out: list):
    if isinstance(gt, dict) or isinstance(pred, dict):
        gt = gt if isinstance(gt, dict) else {}
        pred = pred if isinstance(pred, dict) else {}
        for k in sorted(set(gt) | set(pred)):
            compare(pred.get(k), gt.get(k), f"{path}.{k}" if path else k, out)
        return
    if isinstance(gt, list) or isinstance(pred, list):
        gt = gt if isinstance(gt, list) else []
        pred = pred if isinstance(pred, list) else []
        for i, (p, g) in enumerate(_align(pred, gt)):
            compare(p, g, f"{path}[{i}]", out)
        return
    if _empty(gt) and _empty(pred):
        out.append(("TN", path, pred, gt))
    elif _empty(pred):
        out.append(("FN", path, pred, gt))
    elif _empty(gt) or not leaf_equal(pred, gt, path):
        out.append(("FP", path, pred, gt))
    else:
        out.append(("TP", path, pred, gt))


def f1(c: dict) -> float:
    d = 2 * c["TP"] + c["FP"] + c["FN"]
    return 2 * c["TP"] / d if d else 1.0


def _field_key(path: str) -> str:
    import re
    return re.sub(r"\[\d+\]", "[]", path)


def score_dirs(pred_dir: Path, gt_dir: Path, verbose: bool = False) -> dict:
    total = defaultdict(int)
    per_doc = defaultdict(lambda: defaultdict(int))
    per_field = defaultdict(lambda: defaultdict(int))
    errors = []
    for gt_file in sorted(gt_dir.rglob("*.json")):
        rel = gt_file.relative_to(gt_dir)
        pred_file = pred_dir / rel
        gt = json.loads(gt_file.read_text())
        pred = json.loads(pred_file.read_text()) if pred_file.exists() else {}
        res = []
        compare(pred, gt, "", res)
        for kind, path, p, g in res:
            total[kind] += 1
            per_doc[gt_file.stem][kind] += 1
            per_field[f"{gt_file.stem}:{_field_key(path)}"][kind] += 1
            if kind in ("FP", "FN"):
                errors.append((str(rel), kind, path, p, g))
    report = {
        "f1": f1(total),
        "counts": dict(total),
        "per_doc": {k: round(f1(v), 4) for k, v in per_doc.items()},
        "per_field": {k: {"f1": round(f1(v), 4), **v} for k, v in sorted(per_field.items())},
    }
    if verbose:
        for e in errors:
            print("\t".join(map(str, e)))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pred_dir", type=Path)
    ap.add_argument("gt_dir", type=Path)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)
    r = score_dirs(a.pred_dir, a.gt_dir, a.verbose)
    print(f"\nF1 = {r['f1']:.4f}  {r['counts']}")
    print("per doc:", r["per_doc"])
    print("weakest fields:")
    for k, v in sorted(r["per_field"].items(), key=lambda x: x[1]["f1"])[:15]:
        print(f"  {v['f1']:.3f}  {k}  {dict((x, v[x]) for x in ('TP', 'FP', 'FN', 'TN') if x in v)}")


if __name__ == "__main__":
    sys.exit(main())
