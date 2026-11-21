"""Model sweep: same documents, same pipeline (profile `standard`, one model for everything), many models.

  python -m eval.bench_models MODEL [MODEL ...]      # appends results to docs/bench_sweep.json
Per model: 12 training cases (36 docs + 16 out-of-scope negatives) and the frozen blind set (63 docs + 3 negatives).
Records F1 (overall + per doc type), cost, wall time, errors, size/points (from settings.model_params or the
OpenRouter catalogue name), and whether an EU-headquartered provider serves it.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/bench_sweep.json"
EU_PROVIDERS = {"mistral", "nebius", "inceptron", "nextbit"}
BANDS = [(8, 20), (14, 18), (32, 12), (70, 8), (150, 4)]


def points(b):
    if b is None:
        return None
    for lim, p in BANDS:
        if b <= lim:
            return p
    return 0


def catalogue(model):
    try:
        with urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=30) as r:
            d = json.load(r)["data"]
        provs = sorted({(e.get("tag") or e.get("provider_name") or "").split("/")[0].lower() for e in d.get("endpoints", [])})
        return d.get("name"), provs
    except Exception:  # noqa: BLE001
        return None, []


def size_from_name(name: str | None, model: str):
    txt = f"{name or ''} {model}".replace("-", " ")
    m = re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])", txt)
    return float(m[0]) if m else None


def run(cmd, env, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=ROOT)
        return p.stdout + p.stderr, time.time() - t0, None
    except subprocess.TimeoutExpired:
        return "", time.time() - t0, "timeout"


def main():
    models = sys.argv[1:]
    data = json.loads(OUT.read_text()) if OUT.exists() else {"runs": []}
    import yaml
    params = (yaml.safe_load((ROOT / "config/settings.yaml").read_text()).get("model_params") or {})
    for m in models:
        env = {**os.environ, "O2J_PROFILE": "standard"}
        name, provs = catalogue(m)
        size = (params.get(m) or {}).get("total") or size_from_name(name, m)
        rec = {"model": m, "name": name, "params_b": size, "points": points(size),
               "eu_providers": [p for p in provs if p in EU_PROVIDERS], "providers": provs, "ts": time.time()}
        out, dt, err = run([sys.executable, "run.py", "eval", "--profile", "standard", "--model", m,
                            "--cases", "12", "--workers", "8"], env, 1200)
        mm = re.search(r"F1=([0-9.]+)\s+(\{.*?\}).*?cost=\$([0-9.]+)", out)
        rep = sorted(ROOT.glob(f"runs/*_{m.replace('/', '_')}/report.json"), key=lambda p: p.stat().st_mtime)
        per = json.loads(rep[-1].read_text()).get("per_doc") if rep and mm else None
        rec["train"] = {"f1": float(mm.group(1)) if mm else None, "cost": float(mm.group(3)) if mm else None,
                        "seconds": round(dt), "per_doc": per, "error": err or (None if mm else out[-300:])}
        out, dt, err = run([sys.executable, "-m", "eval.run_blind", "--model", m], env, 1200)
        mb = re.search(r"BLIND F1 = ([0-9.]+)", out)
        mc = re.search(r"cost = \$([0-9.]+)", out)
        mn = re.search(r"returned \{\}: (\d+)/(\d+)", out)
        md = re.search(r"per doctype F1: (\{.*?\})", out)
        rec["blind"] = {"f1": float(mb.group(1)) if mb else None, "cost": float(mc.group(1)) if mc else None,
                        "seconds": round(dt), "negatives_ok": f"{mn.group(1)}/{mn.group(2)}" if mn else None,
                        "per_doc": json.loads(md.group(1).replace("'", '"')) if md else None,
                        "error": err or (None if mb else out[-300:])}
        data["runs"] = [r for r in data["runs"] if r["model"] != m] + [rec]
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"{m:42s} size={size} pts={rec['points']} train={rec['train']['f1']} blind={rec['blind']['f1']} "
              f"cost={rec['train']['cost']}+{rec['blind']['cost']} eu={rec['eu_providers']}", flush=True)


if __name__ == "__main__":
    main()
