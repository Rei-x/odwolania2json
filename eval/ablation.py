"""Step ablation of our pipeline — EVALUATION ONLY (settings overrides + monkeypatches, no production changes).

Cumulative ladder on the same subset as eval/bench_models.py (12 train folders) and optionally the blind set,
same model (Ministral 8B, profile `standard`) except rung g (profile `auto`, 3B -> 8B escalation):

  a  page text + one LLM extraction call with our JSON schema; type chosen by the LLM among the 3 in-scope
     types only (no rules, no vote, no 'inny'); no few-shot, no normalizers, no snap/rules_fill, no verify
  b  + rule/LLM classification vote, out-of-scope -> {}
  c  + few-shot examples (2 nearest training documents)
  d  + deterministic normalisation (YAML normalizers: dates, NIP/KRS/REGON, IBAN, BZP/TED, amounts, persons)
  e  + snap_to_text and rules_fill
  f  + verify -> repair loop (max_rounds 2)            == full profile `standard`
  g  + router/escalation (profile `auto`: rules + 3B, hard documents escalate to 8B)

Always on in every rung (part of the extraction call itself, noted as a caveat): our system prompt with the
field guide, JSON-schema constrained decoding, schema reshaping/enum coercion, derived fields
(czynnosc_opis from czynnosc_powod_id), the empty-result retry, and case-level cross-checks.

  python -m eval.ablation run --rungs a b c d e f g [--blind]     # one subprocess per rung (separate cost meter)
  python -m eval.ablation scan                                       # doc_ori on/off on data/hard_scans/rotated_90
Results: docs/ablation.json (merged per key).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "ablation.json"
RUNGS = "abcdefg"
N_CASES = 12


def save(key: str, rec: dict):
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[key] = {**rec, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def configure(rung: str) -> dict:
    """Return settings for the rung and install the monkeypatches it needs."""
    from o2j import config as C
    from o2j import extract as E
    from o2j import normalize as N
    from o2j import pipeline as PL
    i = RUNGS.index(rung)
    s = C.load_settings(profile="auto" if rung == "g" else "standard")
    s["postprocess"] = {"snap_to_text": i >= 4, "rules_fill": i >= 4}
    if i < 5:
        s["verify"] = {"max_rounds": 0}
    if rung != "g":
        s.setdefault("router", {})["enabled"] = False
    if i < 3:  # no normalizers: values stay as the model wrote them
        N.apply = lambda value, node: value
    if i < 2:  # no few-shot
        E.few_shot_examples = lambda *a, **k: []
    if i < 1:  # classification by one LLM call, forced to an in-scope type (no rules, no vote, no 'inny')
        def llm_only(text, path, specs, llm=None, *a, **k):
            names = list(specs)
            opts = "\n".join(f"- {n}: {sp.description}" for n, sp in specs.items())
            schema = {"type": "object", "properties": {"typ": {"enum": names}}, "required": ["typ"],
                      "additionalProperties": False}
            out, _ = llm.extract_json("Klasyfikujesz dokumenty. Odpowiedz wyłącznie JSON.",
                                      f"Typy:\n{opts}\n\nDokument (początek):\n{text[:5000]}\n\nZwróć {{\"typ\": <jeden z {names}>}}.",
                                      schema, name="classification")
            return out.get("typ", names[0]), {"method": "llm_only"}
        PL.classify = llm_only
    return s


def cmd_one(a):
    """Run one rung in this process (called by `run`)."""
    import run
    s = configure(a.rung)
    run.load_settings = lambda *x, **y: s
    from o2j.llm import COST
    if a.set == "train":
        before = set(ROOT.glob("runs/*/report.json"))
        t0 = time.time()
        run.main(["eval", "--cases", str(N_CASES), "--workers", "8"])
        wall = time.time() - t0
        rep = max(set(ROOT.glob("runs/*/report.json")) - before, key=lambda p: p.stat().st_mtime)
        r = json.loads(rep.read_text())
        el = [json.loads(t.read_text()).get("elapsed_s") for t in (rep.parent / "trace").rglob("*.trace.json")]
        el = [x for x in el if x is not None]
        rec = {"rung": a.rung, "set": "train_subset", "f1": round(r["f1"], 4), "per_doc": r["per_doc"],
               "counts": r["counts"], "cost_usd": round(COST["usd"], 4), "llm_calls": COST["calls"],
               "wall_s": round(wall, 1), "median_s_per_doc": round(statistics.median(el), 2) if el else None,
               "run_dir": str(rep.parent.relative_to(ROOT))}
    else:
        import eval.run_blind as RB
        import o2j.pipeline as PL
        orig = PL.Pipeline.__init__
        PL.Pipeline.__init__ = lambda self, settings=None, model=None, mode=None: orig(self, s, model, mode)
        out = ROOT / "runs" / f"ablation_blind_{a.rung}"
        shutil.rmtree(out, ignore_errors=True)
        t0 = time.time()
        RB.main(["--out", str(out)])
        sm = json.loads((out / "summary.json").read_text())
        rec = {"rung": a.rung, "set": "blind", "f1": sm["f1"], "per_doc": sm["per_doc"],
               "negatives_rejected": sm["negatives_rejected"], "cost_usd": sm["cost_usd"], "llm_calls": sm["llm_calls"],
               "wall_s": round(time.time() - t0, 1)}
    print("ABLATION " + json.dumps(rec, ensure_ascii=False), flush=True)
    save(f"{a.rung}|{rec['set']}", rec)


def cmd_run(a):
    sets = ["train"] + (["blind"] if a.blind else [])
    total = 0.0
    for st in sets:
        for r in a.rungs:
            if total > a.budget:
                print(f"budget {a.budget} reached, stopping before {r}/{st}")
                return
            p = subprocess.run([sys.executable, "-m", "eval.ablation", "one", "--rung", r, "--set", st],
                               capture_output=True, text=True, cwd=ROOT)
            line = next((x for x in p.stdout.splitlines() if x.startswith("ABLATION ")), None)
            if not line:
                print(f"{r}/{st} FAILED: {(p.stdout + p.stderr)[-400:]}")
                return
            rec = json.loads(line[9:])
            total += rec["cost_usd"]
            print(f"{r} {st:6s} F1={rec['f1']}  cost=${rec['cost_usd']:.4f}  wall={rec['wall_s']}s  (total ${total:.3f})", flush=True)


def cmd_scan(a):
    """Orientation step on rotated scans: profile standard with ocr.preprocess [doc_ori] vs []."""
    for name, pre in (("doc_ori_on", "[doc_ori]"), ("doc_ori_off", "[]")):
        p = subprocess.run([sys.executable, "eval/run_with.py", "--set", f"ocr.preprocess={pre}", "--",
                            "eval", "--profile", "standard", "--src", str(a.src)], capture_output=True, text=True, cwd=ROOT,
                           env={**os.environ, "O2J_PROFILE": "standard"})
        import re
        m = re.search(r"F1=([0-9.]+)\s+(\{.*?\}).*?time=([0-9.]+)s\s+cost=\$([0-9.]+)", p.stdout)
        rec = {"variant": name, "src": str(a.src), "f1": float(m.group(1)) if m else None,
               "time_s": float(m.group(3)) if m else None, "cost_usd": float(m.group(4)) if m else None,
               "error": None if m else (p.stdout + p.stderr)[-300:]}
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        save(f"scan|{a.src.name}|{name}", rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "one", "scan"])
    ap.add_argument("--rungs", nargs="+", default=list(RUNGS))
    ap.add_argument("--rung", default="f")
    ap.add_argument("--set", default="train", choices=["train", "blind"])
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--budget", type=float, default=1.5)
    ap.add_argument("--src", type=Path, default=ROOT / "data/hard_scans/rotated_90")
    a = ap.parse_args()
    {"run": cmd_run, "one": cmd_one, "scan": cmd_scan}[a.cmd](a)


if __name__ == "__main__":
    main()
