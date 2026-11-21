"""Dev/test split of the KIO corpus by proceeding (source URL) + adjudicated reference ("gold v2").

gold v2 = Opus reference, with fields where adjudication said our value was right (or both) taken from ours,
and 'neither' replaced by the adjudicator's correct value. Writes runs/kio_gold2/{dev,test}/<doctype>/<file>.json
and runs/kio_split.json. Tuning may only look at the dev half; report on test.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from o2j.case import set_path  # noqa: E402

REF = ROOT / "runs/kio_ref"
KIO = ROOT / "data/kio_raw/pdf"


def main():
    src = {json.loads(l)["file"]: json.loads(l).get("source") or "" for l in open(KIO / "indeks.jsonl")}
    adj = {}
    p = ROOT / "runs/kio_adjudication.jsonl"
    if p.exists():
        for l in open(p):
            r = json.loads(l)
            adj[r["doc"]] = r["fields"]
    out = ROOT / "runs/kio_gold2"
    shutil.rmtree(out, ignore_errors=True)
    split = {"dev": [], "test": []}
    for gt in sorted((REF / "gt").rglob("*.json")):
        rel = str(gt.relative_to(REF / "gt"))
        fname = Path(rel).stem + ".pdf"
        half = "dev" if int(hashlib.sha1(src.get(fname, fname).encode()).hexdigest(), 16) % 2 == 0 else "test"
        g = json.loads(gt.read_text())
        for f in adj.get(rel, []):
            if f["winner"] in ("ours", "both"):
                set_path(g, f["path"], f["ours"])
            elif f["winner"] == "neither":
                set_path(g, f["path"], f["correct"])
        dst = out / half / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
        inp = ROOT / "runs/kio_input" / half / rel.replace(".json", ".pdf")
        inp.parent.mkdir(parents=True, exist_ok=True)
        if not inp.exists():
            shutil.copy(REF / "input" / rel.replace(".json", ".pdf"), inp)
        split[half].append(rel)
    (ROOT / "runs/kio_split.json").write_text(json.dumps(split, indent=1))
    print({k: len(v) for k, v in split.items()})


if __name__ == "__main__":
    main()
