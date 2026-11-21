"""Parser benchmark: our text layer (pypdfium2) vs Docling vs Unstructured — EVALUATION ONLY.

Production code is never modified: the swapped parser is injected by monkeypatching `o2j.pdf.load` with a
loader that serves per-page text produced beforehand by Docling / Unstructured (cached on disk). Everything
else (profile, model, prompts, few-shot, normalisation, verification, case cross-checks, scorer) is the same.
Few-shot example texts also go through the swapped parser, so example and query look alike.

Two venvs, so production requirements stay untouched:

  # 1) parse (Docling / Unstructured live only in .venv-bench)
  .venv-bench/bin/python -m eval.bench_parsers parse --parser docling            # fills the text cache
  .venv-bench/bin/python -m eval.bench_parsers timing --parser docling           # clean timing pass (cold+warm)
  # 2) LLM runs (production .venv)
  .venv/bin/python -m eval.bench_parsers pipeline --parser docling --set train   # our pipeline, swapped text
  .venv/bin/python -m eval.bench_parsers pipeline --parser docling --set blind   # aggregate F1 only
  .venv/bin/python -m eval.bench_parsers baseline --parser docling --set train   # parser + 1 plain LLM call
  .venv/bin/python -m eval.bench_parsers opus --set train                        # Claude Opus reads the PDF
  .venv/bin/python -m eval.bench_parsers det                                     # rules-only throughput

Parsers: pdfium (ours, o2j.pdf.load without OCR), docling (DocumentConverter defaults, forced to CPU,
markdown export per page), unstructured_fast (partition_pdf strategy=fast), unstructured_hires (strategy=hi_res).
Results are appended to docs/bench_parsers.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BENCH = ROOT / "runs" / "bench_parsers"
CACHE = BENCH / "cache"
RESULTS = ROOT / "docs" / "bench_parsers.json"
PARSERS = ("pdfium", "docling", "unstructured_fast", "unstructured_hires")
# same subset as eval/bench_models.py and `run.py eval --cases 12`: negatywne + przyklad_05,10,...,55
N_CASES = 12


def sha(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def train_cases() -> list[str]:
    train = ROOT / "data" / "train"
    cases = sorted(p.name for p in train.iterdir() if p.is_dir())
    return cases[:: max(1, len(cases) // N_CASES)][:N_CASES]


def all_pdfs(which: str) -> list[Path]:
    if which == "subset":
        return sorted(f for c in train_cases() for f in (ROOT / "data/train" / c).glob("*.pdf"))
    roots = {"train": [ROOT / "data/train"], "blind": [ROOT / "data/blind"],
             "all": [ROOT / "data/train", ROOT / "data/blind"]}[which]
    return sorted(f for r in roots for f in r.rglob("*.pdf") if "_build" not in f.parts)


def save_result(key: str, rec: dict):
    data = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    data[key] = {**rec, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ parsers (run in .venv-bench)
def make_parser(name: str):
    """Returns (parse(path) -> list[str] page texts, init_seconds, import_seconds, config description)."""
    t0 = time.time()
    if name == "pdfium":
        from o2j import pdf as P
        t1 = time.time()
        return (lambda p: [pg.text for pg in P.load(p).pages]), 0.0, t1 - t0, "o2j.pdf.load (pypdfium2 + annotation flattening + mojibake fix), no OCR"
    if name == "docling":
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        t1 = time.time()
        opts = PdfPipelineOptions()  # defaults: layout model, table structure, OCR (auto engine) for bitmaps
        opts.accelerator_options = AcceleratorOptions(device="cpu", num_threads=int(os.environ.get("BENCH_THREADS", 4)))
        conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        conv.initialize_pipeline(InputFormat.PDF)
        t2 = time.time()

        def parse(p):
            doc = conv.convert(str(p)).document
            n = max(doc.pages) if doc.pages else 0
            return [doc.export_to_markdown(page_no=i) for i in range(1, n + 1)]
        return parse, t2 - t1, t1 - t0, f"DocumentConverter defaults (do_ocr=True auto engine, table structure), device=cpu, threads={opts.accelerator_options.num_threads}, export_to_markdown(page_no=i)"
    if name.startswith("unstructured"):
        from unstructured.partition.pdf import partition_pdf
        t1 = time.time()
        strategy = "fast" if name.endswith("fast") else "hi_res"
        import pypdfium2 as pdfium

        def parse(p):
            els = partition_pdf(filename=str(p), strategy=strategy, languages=["pol"])
            n = len(pdfium.PdfDocument(str(p)))
            pages = [[] for _ in range(n)]
            for e in els:
                pn = (e.metadata.page_number or 1) - 1
                if 0 <= pn < n and str(e).strip():
                    pages[pn].append(str(e))
            return ["\n\n".join(x) for x in pages]
        init = 0.0
        if strategy == "hi_res":  # load the layout model once outside the timed documents
            t2 = time.time()
            from unstructured_inference.models.base import get_model
            get_model()
            init = time.time() - t2
        return parse, init, t1 - t0, f"partition_pdf(strategy={strategy}, languages=['pol']), elements joined per page"
    raise SystemExit(f"unknown parser {name}")


def cmd_parse(a):
    """Fill the text cache for every PDF (train + blind). Not a timing run (may run alongside other work)."""
    parse, *_ = make_parser(a.parser)
    out = CACHE / a.parser
    out.mkdir(parents=True, exist_ok=True)
    pdfs = all_pdfs(a.which)
    for i, p in enumerate(pdfs, 1):
        dst = out / (sha(p) + ".json")
        if dst.exists():
            continue
        t0 = time.time()
        try:
            pages, err = parse(p), None
        except Exception as e:  # noqa: BLE001
            pages, err = [], repr(e)[:300]
        dt = time.time() - t0
        dst.write_text(json.dumps({"file": str(p.relative_to(ROOT)), "pages": pages, "seconds": round(dt, 3),
                                   "error": err}, ensure_ascii=False))
        print(f"[{i}/{len(pdfs)}] {dt:6.2f}s {p.relative_to(ROOT)}" + (f" ERROR {err}" if err else ""), flush=True)


def cmd_timing(a):
    """Clean timing pass on the train subset: cold (import + init + first doc) and warm per-document times."""
    import platform
    t_proc = time.time()
    parse, init_s, import_s, desc = make_parser(a.parser)
    pdfs = all_pdfs("subset")
    import pypdfium2 as pdfium
    pages = {str(p): len(pdfium.PdfDocument(str(p))) for p in pdfs}
    t0 = time.time()
    parse(pdfs[0])
    first = time.time() - t0
    warm = []
    for p in pdfs:
        t0 = time.time()
        parse(p)
        warm.append((time.time() - t0, pages[str(p)], p.name))
    secs = [w[0] for w in warm]
    digital_docs = [w for w, p in zip(warm, pdfs) if p.parent.name != "negatywne"]
    rec = {"parser": a.parser, "config": desc, "machine": a.machine or platform.node(), "docs": len(pdfs),
           "pages": sum(pages.values()), "import_s": round(import_s, 2), "init_s": round(init_s, 2),
           "first_doc_s": round(first, 2), "cold_total_s": round(import_s + init_s + first, 2),
           "warm_median_s_per_doc": round(statistics.median(secs), 3), "warm_mean_s_per_doc": round(statistics.mean(secs), 3),
           "warm_s_per_page": round(sum(secs) / sum(pages.values()), 3),
           "warm_median_s_inscope_doc": round(statistics.median([w[0] for w in digital_docs]), 3),
           "warm_total_s": round(sum(secs), 2), "process_total_s": round(time.time() - t_proc, 1),
           "slowest": sorted(([round(s, 2), n, pg] for s, n, pg in [(w[0], w[2], w[1]) for w in warm]), reverse=True)[:3]}
    print(json.dumps(rec, ensure_ascii=False, indent=1))
    out = BENCH / f"timing_{a.parser}_{a.machine or 'local'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ injected loader (production .venv)
def install_loader(parser: str):
    """Replace o2j.pdf.load with a cache-backed loader returning the swapped parser's per-page text."""
    from o2j import pdf as P
    if parser == "pdfium":
        return  # production loader, untouched
    cache_dir = CACHE / parser
    missing = []

    def load(path, ocr=None, min_chars=40, dpi=200, max_pages=None, ocr_max_pages=4, prep=None, garbage_threshold=0.1):
        f = cache_dir / (sha(Path(path)) + ".json")
        if not f.exists():
            missing.append(str(path))
            raise FileNotFoundError(f"no {parser} text for {path}")
        d = json.loads(f.read_text())
        pages = d["pages"][:max_pages] if max_pages else d["pages"]
        doc = P.Document(path=Path(path))
        doc.pages = [P.Page(i + 1, (t or "").strip(), "text") for i, t in enumerate(pages)]
        return doc
    P.load = load
    return missing


def parse_seconds(parser: str, files: list[Path]) -> dict[str, float]:
    out = {}
    for f in files:
        c = CACHE / parser / (sha(f) + ".json")
        if c.exists():
            out[str(f)] = json.loads(c.read_text())["seconds"]
    return out


def cmd_pipeline(a):
    os.environ["O2J_PROFILE"] = a.profile
    missing = install_loader(a.parser)
    from o2j.llm import COST
    if a.set == "train":
        import run
        before = set(ROOT.glob("runs/*/report.json"))
        t0 = time.time()
        run.main(["eval", "--cases", str(N_CASES), "--profile", a.profile, "--workers", str(a.workers)])
        wall = time.time() - t0
        rep = max(set(ROOT.glob("runs/*/report.json")) - before, key=lambda p: p.stat().st_mtime)
        r = json.loads(rep.read_text())
        traces = [json.loads(t.read_text()) for t in (rep.parent / "trace").rglob("*.trace.json")]
        el = [t.get("elapsed_s") for t in traces if t.get("elapsed_s") is not None]
        rec = {"setup": "pipeline", "parser": a.parser, "profile": a.profile, "set": "train_subset",
               "f1": round(r["f1"], 4), "per_doc": r["per_doc"], "counts": r["counts"], "docs": len(traces),
               "cost_usd": round(COST["usd"], 4), "llm_calls": COST["calls"], "wall_s": round(wall, 1),
               "pipeline_median_s_per_doc_excl_parse": round(statistics.median(el), 2) if el else None,
               "misclassified": [m["file"] for m in r.get("misclassified", [])], "run_dir": str(rep.parent.relative_to(ROOT)),
               "missing_text": len(missing or [])}
        if a.parser != "pdfium":  # e2e latency = swapped-text pipeline latency + that parser's parse time
            ps = {Path(k).name + "|" + Path(k).parent.name: v for k, v in parse_seconds(a.parser, all_pdfs("subset")).items()}
            e2e = []
            for t in traces:
                f = Path(t["file"])
                if f.name + "|" + f.parent.name in ps and t.get("elapsed_s") is not None:
                    e2e.append(t["elapsed_s"] + ps[f.name + "|" + f.parent.name])
            rec["e2e_median_s_per_doc"] = round(statistics.median(e2e), 2) if e2e else None
        else:
            rec["e2e_median_s_per_doc"] = rec["pipeline_median_s_per_doc_excl_parse"]
    else:
        from eval import run_blind
        out = BENCH / f"blind_{a.parser}_{a.profile}"
        shutil.rmtree(out, ignore_errors=True)
        t0 = time.time()
        run_blind.main(["--out", str(out), "--workers", str(a.workers)])
        s = json.loads((out / "summary.json").read_text())
        rec = {"setup": "pipeline", "parser": a.parser, "profile": a.profile, "set": "blind", "f1": s["f1"],
               "per_doc": s["per_doc"], "docs": s["documents"], "negatives_rejected": s["negatives_rejected"],
               "cost_usd": s["cost_usd"], "llm_calls": s["llm_calls"], "wall_s": round(time.time() - t0, 1),
               "missing_text": len(missing or [])}
    print(json.dumps(rec, ensure_ascii=False))
    save_result(f"pipeline|{a.parser}|{a.profile}|{rec['set']}", rec)


# ------------------------------------------------------------------ "typical approach" baseline
def inscope_docs(which: str) -> list[tuple[str, Path, Path]]:
    """(doctype, pdf, gt_json) for in-scope documents. The baseline gets the TRUE doctype for free (oracle)."""
    docs = []
    if which == "train":
        names = {"odwolanie": (["odwolanie.pdf"], "odwolanie.json"), "pelnomocnictwo": (["pelnomocnictwo.pdf"], "pelnomocnictwo.json"),
                 "przelew": (["przelew.pdf", "potwierdzenie_przelewu.pdf"], "przelew.json")}
        for c in train_cases():
            d = ROOT / "data/train" / c
            for dt, (pdfs, js) in names.items():
                pdf = next((d / n for n in pdfs if (d / n).exists()), None)
                if pdf and (d / js).exists():
                    docs.append((dt, pdf, d / js))
    else:
        m = {"odwolanie.json": ("odwolanie", "odwolanie.pdf"), "pelnomocnictwo.json": ("pelnomocnictwo", "pelnomocnictwo.pdf"),
             "przelew.json": ("przelew", "potwierdzenie_przelewu.pdf")}
        for c in sorted((ROOT / "data/blind").glob("blind_[0-9]*")):
            for js, (dt, pdf) in m.items():
                if (c / js).exists() and (c / pdf).exists():
                    docs.append((dt, c / pdf, c / js))
    return docs


def cmd_baseline(a):
    """Parser text + ONE plain LLM call (organiser template as the only instructions, JSON schema for shape).
    No few-shot, no normalisation, no snapping/rules, no verification, no case cross-checks."""
    os.environ["O2J_PROFILE"] = "standard"
    from concurrent.futures import ThreadPoolExecutor

    from eval.opus_reference import system_for
    from eval.score import score_dirs
    from o2j.config import load_settings
    from o2j.llm import COST, LLM, PROVIDERS
    from o2j.spec import load_specs
    from o2j import pdf as P
    s = load_settings(profile="standard")
    PROVIDERS.update(s.get("providers") or {})
    llm = LLM(s["llm"])
    specs = load_specs(s["paths"]["doctypes"])
    install_loader(a.parser)
    docs = inscope_docs(a.set)
    out = BENCH / f"baseline_{a.parser}_{a.set}"
    shutil.rmtree(out, ignore_errors=True)
    lat = []

    def one(job):
        dt, pdf, js = job
        rel = Path(pdf.parent.name) / (pdf.stem + ".json")
        (out / "gt" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(js, out / "gt" / rel)
        t0 = time.time()
        try:
            doc = P.load(pdf)
            text = "\n\n".join(p.text for p in doc.pages[:6])  # same 6-page cap as the Opus reference
            res, _ = llm.extract_json(system_for(dt), f"Dokument (typ: {dt}):\n\n{text}\n\nZwróć wyłącznie obiekt JSON.",
                                      specs[dt].json_schema(), name=dt)
        except Exception as e:  # noqa: BLE001
            print("  error", type(e).__name__, str(e)[:120], flush=True)
            res = {}
        lat.append(time.time() - t0)
        (out / "pred" / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / "pred" / rel).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, docs))
    wall = time.time() - t0
    r = score_dirs(out / "pred", out / "gt")
    ps = parse_seconds(a.parser, [d[1] for d in docs]) if a.parser != "pdfium" else {}
    rec = {"setup": "baseline_single_call", "parser": a.parser, "model": llm.model, "set": a.set + ("_subset" if a.set == "train" else ""),
           "docs": len(docs), "f1": round(r["f1"], 4), "per_doc": r["per_doc"], "counts": r["counts"],
           "cost_usd": round(COST["usd"], 4), "llm_calls": COST["calls"], "wall_s": round(wall, 1),
           "llm_median_s_per_doc": round(statistics.median(lat), 2),
           "e2e_median_s_per_doc": round(statistics.median([l + ps.get(str(d[1]), 0) for l, d in zip(lat, docs)]), 2) if ps else None,
           "note": "oracle doctype given; in-scope documents only"}
    if a.set == "blind":  # aggregate only: drop per-document outputs
        rec["per_field"] = None
        shutil.rmtree(out, ignore_errors=True)
    print(json.dumps(rec, ensure_ascii=False))
    save_result(f"baseline|{a.parser}|{rec['set']}", rec)


def cmd_opus(a):
    """Claude Opus via the Anthropic API (ANTHROPIC_API_KEY, anthropic SDK) reading the PDF natively, with the
    organiser template only (eval/opus_reference.annotate). Hard budget cap."""
    from concurrent.futures import ThreadPoolExecutor
    import threading

    import anthropic

    from eval.opus_reference import annotate
    from eval.score import score_dirs
    from o2j.spec import load_specs
    specs = load_specs(ROOT / "config/doctypes")
    client = anthropic.Anthropic()  # direct Anthropic API, never OpenRouter
    docs = inscope_docs(a.set)
    out = BENCH / f"opus_{a.set}"
    spent = {"usd": float(a.spent), "n": 0, "skipped": 0}
    lock = threading.Lock()
    lat = []

    def one(job):
        dt, pdf, js = job
        rel = Path(pdf.parent.name) / (pdf.stem + ".json")
        pf = out / "pred" / rel
        (out / "gt" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(js, out / "gt" / rel)
        if pf.exists():
            return
        with lock:
            if spent["usd"] > a.budget - 0.3:
                spent["skipped"] += 1
                return
        t0 = time.time()
        try:
            r = annotate(client, specs, dt, pdf)
        except Exception as e:  # noqa: BLE001
            print("  error", type(e).__name__, str(e)[:160], flush=True)
            return
        lat.append(time.time() - t0)
        with lock:
            spent["usd"] += r["cost"]
            spent["n"] += 1
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(json.dumps(r["result"], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {spent['n']} ${spent['usd']:.2f}", flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, docs))
    # score only documents Opus actually annotated
    gt_used = out / "gt_used"
    shutil.rmtree(gt_used, ignore_errors=True)
    for p in (out / "pred").rglob("*.json"):
        rel = p.relative_to(out / "pred")
        (gt_used / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out / "gt" / rel, gt_used / rel)
    r = score_dirs(out / "pred", gt_used)
    n = len(list((out / "pred").rglob("*.json")))
    rec = {"setup": "opus_reference", "model": "claude-opus-5-5 (Anthropic API, native PDF, effort=high)", "set": a.set,
           "docs_scored": n, "docs_total": len(docs), "f1": round(r["f1"], 4), "per_doc": r["per_doc"], "counts": r["counts"],
           "cost_usd_cumulative": round(spent["usd"], 3), "median_s_per_doc": round(statistics.median(lat), 1) if lat else None,
           "skipped_budget": spent["skipped"], "note": "oracle doctype given; organiser template only; in-scope documents"}
    if a.set == "blind":
        shutil.rmtree(out / "gt", ignore_errors=True)
        shutil.rmtree(gt_used, ignore_errors=True)
    print(json.dumps(rec, ensure_ascii=False))
    save_result(f"opus|{a.set}", rec)


def cmd_det(a):
    """Rules-only profile (no LLM) on the train subset: F1 and throughput, 1 worker and 8 workers."""
    import run
    for w in (1, 8):
        before = set(ROOT.glob("runs/*/report.json"))
        t0 = time.time()
        run.main(["eval", "--cases", str(N_CASES), "--profile", "deterministyczny", "--workers", str(w)])
        wall = time.time() - t0
        rep = max(set(ROOT.glob("runs/*/report.json")) - before, key=lambda p: p.stat().st_mtime)
        r = json.loads(rep.read_text())
        traces = [json.loads(t.read_text()) for t in (rep.parent / "trace").rglob("*.trace.json")]
        el = [t["elapsed_s"] for t in traces if t.get("elapsed_s") is not None]
        rec = {"setup": "deterministic", "parser": "pdfium", "set": "train_subset", "workers": w, "f1": round(r["f1"], 4),
               "per_doc": r["per_doc"], "docs": len(traces), "wall_s": round(wall, 2),
               "docs_per_s": round(len(traces) / r["elapsed_s"], 2), "median_s_per_doc": round(statistics.median(el), 3),
               "pipeline_elapsed_s": r["elapsed_s"], "cost_usd": 0.0}
        print(json.dumps(rec, ensure_ascii=False))
        save_result(f"deterministic|train_subset|w{w}", rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["parse", "timing", "pipeline", "baseline", "opus", "det"])
    ap.add_argument("--parser", choices=PARSERS, default="pdfium")
    ap.add_argument("--which", default="all", choices=["all", "train", "blind", "subset"])
    ap.add_argument("--set", default="train", choices=["train", "blind"])
    ap.add_argument("--profile", default="standard")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--machine", default=None)
    ap.add_argument("--budget", type=float, default=5.0)
    ap.add_argument("--spent", type=float, default=0.0, help="opus: dollars already spent in earlier runs")
    a = ap.parse_args()
    {"parse": cmd_parse, "timing": cmd_timing, "pipeline": cmd_pipeline, "baseline": cmd_baseline,
     "opus": cmd_opus, "det": cmd_det}[a.cmd](a)


if __name__ == "__main__":
    main()
