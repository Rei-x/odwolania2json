"""Web GUI: wgraj PDF -> analiza -> podgląd dokumentu obok wyodrębnionych danych, z podświetleniem źródła.

  python gui.py            # http://127.0.0.1:8000
"""
from __future__ import annotations

import io
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from o2j.pdf import _PDFIUM_LOCK, flat_page  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

DATA = ROOT / "gui_data"
app = FastAPI(title="Wróbelek")
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402

app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def basic_auth(request, call_next):
    """Optional HTTP Basic Auth (env O2J_GUI_PASSWORD, user O2J_GUI_USER default 'uzp') — required when the GUI
    is exposed beyond localhost, e.g. through a tunnel."""
    import base64
    import os
    import secrets
    pw = os.environ.get("O2J_GUI_PASSWORD")
    if pw:
        user = os.environ.get("O2J_GUI_USER", "uzp")
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(hdr[6:]).decode().partition(":")
                ok = secrets.compare_digest(u, user) and secrets.compare_digest(p, pw)
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            return Response("Wymagane logowanie", status_code=401, headers={"WWW-Authenticate": 'Basic realm="wrobelek"'})
    return await call_next(request)
_pipes: dict[tuple[str, str], Pipeline] = {}
PROFILE_INFO = {
    "deterministyczny": "Reguły bez LLM — najtańszy, w pełni powtarzalny",
    "ekonomiczny": "Tani model, bez pętli naprawy",
    "standard": "Szybki model + weryfikacja i naprawa",
    "maksymalny": "Głosowanie kilku przebiegów/modeli — najwyższa jakość",
}


EU_PROVIDERS = {"mistral", "nebius", "nextbit", "inceptron", "scaleway", "ovhcloud", "aleph-alpha"}  # siedziba w UE/EOG
BENCH = ROOT / "docs" / "benchmarks.json"


def _sweep_path() -> Path:
    import os
    return Path(os.environ.get("O2J_BENCH_SWEEP") or ROOT / "docs" / "bench_sweep.json")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # brak pliku albo zapis w toku (sweep dopisuje wyniki)
        return default


def _points(b) -> int | None:
    if b is None:
        return None
    for lim, pts in ((8, 20), (14, 18), (32, 12), (70, 8), (150, 4)):
        if b <= lim:
            return pts
    return 0


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _eu_slugs(provs) -> list[str]:
    return sorted({str(p).split("/")[0].lower() for p in provs or [] if str(p).split("/")[0].lower() in EU_PROVIDERS})


def model_catalog() -> list[dict]:
    """settings.model_params + settings.providers + docs/bench_sweep.json + docs/benchmarks.json -> lista modeli do wyboru."""
    from o2j.config import load_settings
    s = load_settings()
    params, provs = s.get("model_params") or {}, s.get("providers") or {}
    bench = {m["id"]: m for m in (_read_json(BENCH, {}).get("models") or []) if m.get("id")}
    sweep = {r["model"]: r for r in (_read_json(_sweep_path(), {}).get("runs") or []) if r.get("model")}
    ids = [m for m in list(params) + list(provs) + list(sweep) if m != "deterministic"]
    out = []
    for mid in dict.fromkeys(ids):
        b, r, cfg = bench.get(mid) or {}, sweep.get(mid) or {}, provs.get(mid) or {}
        size = (params.get(mid) or {}).get("total")
        size = size if size is not None else _num(r.get("params_b")) if _num(r.get("params_b")) is not None else b.get("params_b")
        pinned = _eu_slugs(cfg.get("only"))
        eu_sweep = _eu_slugs(r.get("eu_providers"))
        tr, bl = ({k: _num(v) for k, v in (r.get(part) or {}).items() if k in ("f1", "cost")} for part in ("train", "blind"))
        f1b = bl.get("f1") if bl.get("f1") is not None else (b.get("f1") or {}).get("blind")
        f1t = tr.get("f1") if tr.get("f1") is not None else (b.get("f1") or {}).get("train")
        cost = tr.get("cost") if tr.get("cost") is not None else (b.get("cost_usd") or {}).get("train")
        out.append({"id": mid, "name": b.get("name") or re.sub(r"^[^:]{1,30}:\s*", "", r.get("name") or "") or mid.split("/")[-1], "params_b": size,
                    "active_b": (params.get(mid) or {}).get("active"), "points": _points(size),
                    "eu": bool(pinned or (eu_sweep and not cfg.get("only"))), "eu_providers": pinned or eu_sweep,
                    "pinned": bool(pinned), "f1_blind": f1b, "f1_train": f1t, "cost": cost, "cost_blind": bl.get("cost"),
                    "in_sweep": bool(r), "configured": mid in params or mid in provs})
    out.sort(key=lambda m: (not m["eu"], -(m["points"] if m["points"] is not None else -1), -(m["f1_blind"] or 0), m["name"]))
    return out


def settings_for(profile: str | None = None, model: str | None = None) -> dict:
    """Ustawienia profilu; wybrany model nadpisuje llm.model, classification.model i ocr.model (jeden model na wszystko)."""
    from o2j.config import load_settings
    s = load_settings(profile=profile)
    if not model or (s.get("extraction") or {}).get("mode") == "deterministic":
        return s
    s["llm"]["model"] = model
    s.setdefault("classification", {})["model"] = model
    s.setdefault("ocr", {})["model"] = model
    # żaden inny model nie wchodzi tylnymi drzwiami: bez głosu innych modeli i bez eskalacji w kaskadzie
    s["classification"]["vote_models"] = []
    if (s.get("voting") or {}).get("models"):
        s["voting"]["models"] = [model]
    if (s.get("router") or {}).get("enabled"):
        s["router"]["enabled"] = False
    provs = s.setdefault("providers", {})
    if not (provs.get(model) or {}).get("only"):  # bez przypięcia w konfiguracji: dostawcy z UE znalezieni w sweepie
        run = next((r for r in (_read_json(_sweep_path(), {}).get("runs") or []) if r.get("model") == model), {})
        eu = _eu_slugs(run.get("eu_providers"))
        if eu:
            provs[model] = {**(provs.get(model) or {}), "only": eu, "allow_fallbacks": False, "data_collection": "deny"}
    s["model_override"] = model
    return s


def get_pipe(profile: str | None = None, model: str | None = None) -> Pipeline:
    key = (profile or "", model or "")
    if key not in _pipes:
        _pipes[key] = Pipeline(settings_for(profile, model))
    return _pipes[key]


def _safe(sid: str, name: str) -> Path:
    path = (DATA / sid / name).resolve()
    if DATA.resolve() not in path.parents or not path.exists():
        raise HTTPException(404)
    return path


def _norm(s: str) -> str:
    return " ".join(s.split())


def highlight_rects(pdf_path: Path, evidence: list[dict]) -> None:
    """Attach `rects` (page-relative %, top-left origin) to located evidence using the PDF text layer."""
    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(pdf_path))
        cache = {}
        for e in evidence:
            if e.get("method") != "located" or not e.get("page"):
                continue
            n = e["page"] - 1
            if n >= len(pdf):
                continue
            if n not in cache:
                page = flat_page(pdf, n)
                tp = page.get_textpage()
                w, h = page.get_size()
                full = tp.get_text_range()
                # map collapsed-whitespace text positions back to char indices
                idx, buf, prev_space = [], [], False
                for i, ch in enumerate(full):
                    if ch.isspace():
                        if not prev_space and buf:
                            buf.append(" ")
                            idx.append(i)
                        prev_space = True
                    else:
                        buf.append(ch)
                        idx.append(i)
                        prev_space = False
                cache[n] = (tp, w, h, "".join(buf).lower(), idx)
            tp, w, h, text, idx = cache[n]
            q = _norm(e.get("quote", "")).lower()
            pos = text.find(q) if q else -1
            if pos < 0:
                continue
            a, b = idx[pos], idx[min(pos + len(q), len(idx)) - 1] + 1
            rects = []
            for r in range(tp.count_rects(a, b - a)):
                l, bt, rt, tp_ = tp.get_rect(r)
                rects.append([round(l / w * 100, 3), round((h - tp_) / h * 100, 3),
                              round((rt - l) / w * 100, 3), round((tp_ - bt) / h * 100, 3)])
            if rects:
                e["rects"] = rects
        for tp, *_ in cache.values():
            tp.close()
        pdf.close()


STATIC = ROOT / "o2j" / "static"
SAMPLES = ROOT / "samples"
DIST = STATIC / "dist"  # React SPA built from web/ (npm run build); committed, so no Node is needed to run
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
if DIST.is_dir():
    app.mount("/dist", StaticFiles(directory=str(DIST)), name="dist")


def _page(legacy: str) -> str:
    """SPA shell when the React build exists, otherwise the legacy static page."""
    spa = DIST / "index.html"
    return (spa if spa.exists() else STATIC / legacy).read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def landing():
    return _page("landing.html")


@app.get("/app", response_class=HTMLResponse)
def index():
    return _page("index.html")


@app.get("/nowy-typ", response_class=HTMLResponse)
def wizard_page():
    return _page("index.html")


@app.get("/api/samples")
def samples():
    """Trudne przykładowe dokumenty (samples/samples.json) do wypróbowania w GUI."""
    try:
        items = json.loads((SAMPLES / "samples.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{k: it.get(k) for k in ("name", "title", "opis", "kind", "typ", "files") if it.get(k) is not None} for it in items]


@app.get("/samples/{name}")
def sample_file(name: str):
    path = (SAMPLES / name).resolve()
    if path.parent != SAMPLES.resolve() or path.suffix.lower() not in (".pdf", ".webp") or not path.is_file():
        raise HTTPException(404)
    if path.suffix.lower() == ".webp":  # miniatura do strony startowej
        return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@app.get("/api/doctypes")
def doctypes():
    return [{"name": n, "description": s.description} for n, s in get_pipe().specs.items()]


@app.get("/api/profiles")
def profiles():
    from o2j.config import load_settings
    s = load_settings()
    names = list((s.get("profiles") or {}).keys())
    return {"default": s.get("profile"), "profiles": [{"name": n, "opis": PROFILE_INFO.get(n, "")} for n in names]}


@app.get("/api/models")
def models():
    """Modele do ręcznego wyboru w aplikacji (rozmiar, punkty UZP, hosting w UE, F1 ze sweepu/benchmarków)."""
    return {"default": None, "models": model_catalog()}


@app.post("/api/process")
async def process(files: list[UploadFile] = File(...), case: str | None = Form(None), profile: str | None = Form(None),
                  model: str | None = Form(None)):
    model = (model or "").strip() or None
    if model and model not in {m["id"] for m in model_catalog()}:
        raise HTTPException(400, f"Nieznany model: {model}")
    sid = case if case and case.isalnum() and len(case) <= 32 else uuid.uuid4().hex[:10]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            continue
        path = d / name
        k = 2
        while path.exists():  # several cases uploaded together often reuse names (odwolanie.pdf …)
            path = d / f"{Path(name).stem} ({k}){Path(name).suffix}"
            k += 1
        path.write_bytes(await f.read())
        out.append(await run_in_threadpool(_one, sid, path, profile, model))
    if not out:
        raise HTTPException(400, "Brak plików PDF")
    return {"session": sid, "documents": out}


def _one(sid: str, path: Path, profile: str | None = None, model: str | None = None) -> dict:
    p = get_pipe(profile, model)
    try:
        doctype, result, trace = p.process(path)
    except Exception as e:  # noqa: BLE001
        return {"session": sid, "file": path.name, "doctype": "error", "error": str(e), "result": {}, "trace": {}}
    evidence = trace.get("evidence") or []
    try:
        highlight_rects(path, evidence)
    except Exception:  # noqa: BLE001
        pass
    (path.parent / (path.stem + ".json")).write_text(
        json.dumps(result if doctype in p.specs else {}, ensure_ascii=False, indent=2), encoding="utf-8")
    (path.parent / (path.stem + ".result.json")).write_text(json.dumps({
        "doctype": doctype, "result": result, "file": path.name, "profile": p.s.get("active_profile"),
        "model_override": p.s.get("model_override"), "text": "\n".join(pg.get("text", "") for pg in trace.get("page_texts", []))}, ensure_ascii=False), encoding="utf-8")
    keep = ("classification", "model", "pages", "ocr_pages", "elapsed_s", "few_shot", "verification", "usage",
            "voting", "learned_examples_available", "active_profile", "router", "model_override", "ocr_model")
    trace["active_profile"] = p.s.get("active_profile")
    trace["model_override"] = p.s.get("model_override")
    trace["ocr_model"] = (p.s.get("ocr") or {}).get("model") or p.s["llm"].get("model") if trace.get("ocr_pages") else None
    return {"session": sid, "file": path.name, "doctype": doctype, "result": result,
            "trace": {**{k: trace.get(k) for k in keep}, "evidence": evidence}}


@app.get("/api/case/{sid}")
def case_report(sid: str):
    """Cross-document consistency of all documents uploaded in one case (session)."""
    from o2j.case import analyze_case, load_case_rules
    d = (DATA / sid).resolve()
    if DATA.resolve() not in d.parents or not d.exists():
        raise HTTPException(404)
    p = get_pipe()
    docs = {}
    for f in sorted(d.glob("*.result.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["doctype"] in p.specs:
            docs[r["file"]] = {"doctype": r["doctype"], "result": json.loads(json.dumps(r["result"])), "text": r["text"]}
    rules = load_case_rules(ROOT / "config" / "case.yaml")
    return analyze_case(docs, rules) if docs else {"dokumenty": {}, "kontrole": [], "uzupelnienia_krzyzowe": []}


@app.post("/api/feedback")
def feedback(payload: dict = Body(...)):
    """User approved (optionally corrected) a result -> memory (few-shot pool + quality stats)."""
    sid, name, corrected = payload.get("session"), payload.get("file"), payload.get("corrected")
    pdf = _safe(sid, name)
    r = json.loads((pdf.parent / (pdf.stem + ".result.json")).read_text(encoding="utf-8"))
    p = get_pipe()
    if r["doctype"] not in p.specs:
        raise HTTPException(400, "Dokument spoza obsługiwanych typów")
    from o2j.extract import postprocess
    corrected = postprocess(p.specs[r["doctype"]], corrected)  # same normalisation as the pipeline
    meta = p.memory.add(pdf, r["doctype"], r["result"], corrected, source="gui")
    return {"saved": True, "corrected_fields": meta["corrected"], "changes": meta["changes"], "stats": p.memory.stats()}


@app.get("/api/stats")
def stats():
    return get_pipe().memory.stats()


@app.get("/api/page/{sid}/{name}/{n}.png")
def page_png(sid: str, name: str, n: int, scale: float = 2.0):
    path = _safe(sid, name)
    cache = path.parent / f".{path.stem}.p{n}.s{scale}.png"
    if not cache.exists():
        with _PDFIUM_LOCK:
            pdf = pdfium.PdfDocument(str(path))
            if not 1 <= n <= len(pdf):
                raise HTTPException(404)
            img = pdf[n - 1].render(scale=scale).to_pil()
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            cache.write_bytes(buf.getvalue())
            pdf.close()
    return Response(cache.read_bytes(), media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/files/{sid}/{name}")
def files(sid: str, name: str):
    path = _safe(sid, name)
    media = "application/pdf" if path.suffix == ".pdf" else "application/json"
    return FileResponse(path, media_type=media, headers={"Content-Disposition": f'inline; filename="{path.name}"'})


# ---------------------------------------------------------------- kreator nowego typu dokumentu
def _doctypes_dir() -> Path:
    from o2j.config import load_settings
    return Path(load_settings()["paths"]["doctypes"])


def _doctype_file(name: str) -> Path:
    from o2j.wizard import NAME_RE
    if not NAME_RE.match(name or ""):
        raise HTTPException(400, "Nazwa typu: małe litery, cyfry i _, zaczyna się literą (np. faktura)")
    return _doctypes_dir() / f"{name}.yaml"


@app.get("/api/doctypes/list")
def doctypes_list():
    """Wszystkie typy z config/doctypes/ z informacją, czy są wbudowane (tylko do odczytu w kreatorze)."""
    import yaml as _yaml

    from o2j.wizard import BUILTIN, _count
    out = []
    for p in sorted(_doctypes_dir().glob("*.yaml")):
        try:
            d = _yaml.safe_load(p.read_text(encoding="utf-8"))
            n_fields = _count(d.get("fields") or {})
        except Exception as e:  # noqa: BLE001
            out.append({"name": p.stem, "file": p.name, "error": str(e), "builtin": p.stem in BUILTIN})
            continue
        out.append({"name": d.get("name", p.stem), "file": p.name, "description": d.get("description", ""),
                    "builtin": d.get("name", p.stem) in BUILTIN, "fields": n_fields,
                    "keywords": len((d.get("classify") or {}).get("keywords") or {}),
                    "deterministic": bool(d.get("deterministic"))})
    return out


@app.get("/api/doctypes/meta")
def doctypes_meta():
    """Słowniki dla edytora pól: typy, normalizatory (o2j.normalize.NORMALIZERS), typy wbudowane."""
    from o2j.normalize import NORMALIZERS
    from o2j.wizard import BUILTIN, TYPES
    return {"types": sorted(TYPES), "normalizers": list(NORMALIZERS), "builtin": sorted(BUILTIN)}


@app.get("/api/doctypes/{name}/yaml")
def doctype_yaml(name: str):
    from o2j.wizard import BUILTIN
    p = _doctype_file(name)
    if not p.is_file():
        raise HTTPException(404, "Nie ma takiego typu")
    return {"name": name, "yaml": p.read_text(encoding="utf-8"), "builtin": name in BUILTIN}


@app.post("/api/doctypes/draft")
def doctype_draft(payload: dict = Body(...)):
    """Szablon JSON z komentarzami // (styl organizatora) albo tabela pól -> szkic YAML + sparsowana specyfikacja."""
    from o2j import wizard as W
    try:
        spec = W.draft(payload.get("name") or "", payload.get("title") or "", payload.get("description") or "",
                       template=payload.get("template"), rows=payload.get("fields"))
    except W.TemplateError as e:
        raise HTTPException(422, {"msg": f"Szablon JSON: {e}", "line": e.line}) from e
    if not spec["fields"]:
        raise HTTPException(422, {"msg": "Brak pól — dodaj co najmniej jedno pole.", "line": None})
    text = W.to_yaml(spec)
    return {"yaml": text, "spec": spec, "validation": W.validate(text)}


@app.post("/api/doctypes/validate")
def doctype_validate(payload: dict = Body(...)):
    from o2j import wizard as W
    res = W.validate(payload.get("yaml") or "")
    if res.get("name") in W.BUILTIN:
        res["warnings"].insert(0, {"line": 1, "path": "name", "msg": f"'{res['name']}' to typ wbudowany — zapis go nadpisze."})
    elif res.get("name") and (_doctypes_dir() / f"{res['name']}.yaml").exists():
        res["warnings"].insert(0, {"line": 1, "path": "name", "msg": f"Typ '{res['name']}' już istnieje — zapis zaktualizuje plik."})
    return res


@app.post("/api/doctypes/test")
async def doctype_test(file: UploadFile = File(...), yaml_text: str = Form(..., alias="yaml"),
                       profile: str | None = Form(None)):
    """Ekstrakcja przykładowego PDF szkicem specyfikacji, bez zapisywania typu (nic nie trafia do config/)."""
    from o2j import wizard as W
    v = W.validate(yaml_text)
    if not v["ok"]:
        raise HTTPException(422, {"msg": "Specyfikacja zawiera błędy — popraw YAML przed testem.", "errors": v["errors"]})
    name = Path(file.filename or "dokument.pdf").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Wgraj plik PDF")
    sid = "wiz" + uuid.uuid4().hex[:8]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    path.write_bytes(await file.read())
    return await run_in_threadpool(_test_draft, sid, path, yaml_text, profile)


def _test_draft(sid: str, path: Path, yaml_text: str, profile: str | None) -> dict:
    import time

    from o2j import extract as E
    from o2j import pdf as P
    from o2j import verify as V
    from o2j import wizard as W
    from o2j.classify import rule_scores
    from o2j.llm import COST
    t0 = time.time()
    spec = W.load_spec_text(yaml_text)
    pipe = get_pipe(profile)
    if pipe.llm is None:  # profil Reguły nie ma LLM; nowy typ nie ma jeszcze reguł deterministycznych
        pipe = get_pipe(None)
    if pipe.llm is None:
        raise HTTPException(400, "Test wymaga profilu z modelem LLM")
    ocr_cfg = pipe.s.get("ocr", {})
    doc = P.load(path, ocr=pipe._ocr, min_chars=int(ocr_cfg.get("min_chars_per_page", 40)), dpi=int(ocr_cfg.get("dpi", 200)),
                 ocr_max_pages=int(ocr_cfg.get("max_pages", 4)), prep=ocr_cfg.get("preprocess"),
                 garbage_threshold=float(ocr_cfg.get("garbage_threshold", 0.1)))
    full = doc.text()
    # podgląd klasyfikacji regułami: szkic na tle aktualnie aktywnych typów (bez LLM)
    specs = {**{k: s for k, s in pipe.specs.items() if k != spec.name}, spec.name: spec}
    use_fn = bool(pipe.s.get("classification", {}).get("use_filename", False))  # same as the pipeline
    scores = rule_scores(full[:6000], path.name if use_fn else "", specs)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    min_score = float(pipe.s.get("classification", {}).get("min_score", 3))
    second = ranked[1][1] if len(ranked) > 1 else 0
    cls = {"scores": dict(ranked), "best": ranked[0][0], "min_score": min_score,
           "confident": ranked[0][0] == spec.name and scores[spec.name] >= min_score and scores[spec.name] - second >= 2}
    text = doc.text(spec.pages)
    if not text.strip():
        raise HTTPException(422, "Dokument nie zawiera czytelnego tekstu")
    examples = E.few_shot_examples(spec, pipe.s["paths"].get("train"), text, set(), spec.few_shot)
    system, user = E.build_prompt(spec, text, examples)
    images = [p.image for p in doc.pages[: spec.pages or len(doc.pages)] if p.source == "ocr" and p.image] or None
    if images:
        user += "\n\nUWAGA: tekst pochodzi z OCR skanu; dołączono obrazy stron — w razie wątpliwości rozstrzygaj na podstawie obrazu."
    usd0 = COST["usd"]
    raw, meta = pipe.llm.extract_json(system, user, spec.json_schema(), name=spec.name, images=images)
    result = E.postprocess(spec, raw)
    evidence = E.ground(doc, result, E.derived_fields(spec))
    issues = V.verify(spec, result, evidence, ocr_doc=bool(images))
    try:
        highlight_rects(path, evidence)
    except Exception:  # noqa: BLE001
        pass
    return {"session": sid, "file": path.name, "doctype": spec.name, "result": result,
            "trace": {"pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"],
                      "model": meta.get("model"), "usage": meta.get("usage"), "cost_usd": round(COST["usd"] - usd0, 5),
                      "elapsed_s": round(time.time() - t0, 2), "few_shot": len(examples), "classification": cls,
                      "issues": issues, "evidence": evidence, "active_profile": pipe.s.get("active_profile")}}


@app.post("/api/doctypes/infer")
async def doctype_infer(files: list[UploadFile] = File(...)):
    """Przykładowy PDF (lub kilka) -> LLM proponuje kompletny typ (nazwa, opis, słowa kluczowe, pola) -> YAML po walidacji.
    Nic nie trafia do config/; zapis jak zwykle przez POST /api/doctypes."""
    if not files:
        raise HTTPException(400, "Wgraj przykładowy PDF")
    sid = "wiz" + uuid.uuid4().hex[:8]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in files[:5]:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"{name}: wgraj plik PDF")
        p = d / name
        p.write_bytes(await f.read())
        paths.append(p)
    return await run_in_threadpool(_infer_doctype, sid, paths)


def _infer_model(s: dict) -> str | None:
    """Model kreatora: najmocniejszy mały model profilu (klasyfikacyjny 8B w 'auto', inaczej model ekstrakcji)."""
    return (s.get("classification") or {}).get("model") or (s.get("llm") or {}).get("model")


def _infer_doctype(sid: str, paths: list[Path]) -> dict:
    import time

    from o2j import pdf as P
    from o2j import wizard as W
    from o2j.llm import COST
    t0 = time.time()
    pipe = get_pipe(None)
    if pipe.llm is None:  # profil bez LLM (Reguły): kreator potrzebuje modelu
        pipe = get_pipe("standard")
    if pipe.llm is None:
        raise HTTPException(400, "Kreator wymaga profilu z modelem LLM")
    ocr_cfg = pipe.s.get("ocr", {})
    texts = []
    for p in paths:
        doc = P.load(p, ocr=pipe._ocr, min_chars=int(ocr_cfg.get("min_chars_per_page", 40)), dpi=int(ocr_cfg.get("dpi", 200)),
                     ocr_max_pages=int(ocr_cfg.get("max_pages", 4)), prep=ocr_cfg.get("preprocess"),
                     garbage_threshold=float(ocr_cfg.get("garbage_threshold", 0.1)))
        texts.append(doc.text(4))
    if not any(t.replace("=== Strona", "").strip() for t in texts):
        raise HTTPException(422, "Dokument nie zawiera czytelnego tekstu")
    taken = {p.stem for p in _doctypes_dir().glob("*.yaml")}
    model = _infer_model(pipe.s)
    usd0 = COST["usd"]
    try:
        res = W.infer(texts, pipe.llm, model=model, taken=taken, pages=3,
                      reference=W.reference_texts(pipe.s["paths"].get("train")), specs=pipe.specs,
                      min_score=float(pipe.s.get("classification", {}).get("min_score", 3)))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"session": sid, "files": [p.name for p in paths], "yaml": res["yaml"], "spec": res["spec"],
            "validation": res["validation"], "warnings": res["warnings"], "model": res["meta"].get("model") or model,
            "cost": round(COST["usd"] - usd0, 5), "elapsed_s": round(time.time() - t0, 2)}


@app.post("/api/doctypes")
def doctype_save(payload: dict = Body(...)):
    """Zapis config/doctypes/<nazwa>.yaml; typ jest od razu aktywny (klasyfikacja + ekstrakcja), bez restartu."""
    from o2j import wizard as W
    text = payload.get("yaml") or ""
    v = W.validate(text)
    if not v["ok"]:
        raise HTTPException(422, {"msg": "Specyfikacja zawiera błędy.", "errors": v["errors"]})
    name = v["name"]
    path = _doctype_file(name)
    if name in W.BUILTIN and not payload.get("overwrite_builtin"):
        raise HTTPException(409, f"'{name}' to typ wbudowany — nadpisanie wymaga jawnej zgody (overwrite_builtin).")
    if path.exists() and name not in W.BUILTIN and not payload.get("overwrite"):
        raise HTTPException(409, f"Typ '{name}' już istnieje — potwierdź aktualizację (overwrite).")
    existed = path.exists()
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    _pipes.clear()  # nowe Pipeline wczyta specyfikacje od nowa
    return {"saved": True, "name": name, "file": str(path.relative_to(ROOT)), "updated": existed,
            "active": name in get_pipe().specs}


@app.delete("/api/doctypes/{name}")
def doctype_delete(name: str):
    from o2j.wizard import BUILTIN
    p = _doctype_file(name)
    if name in BUILTIN:
        raise HTTPException(403, "Typów wbudowanych nie można usunąć z GUI")
    if not p.is_file():
        raise HTTPException(404, "Nie ma takiego typu")
    p.unlink()
    _pipes.clear()
    return {"deleted": name}


# ---------------------------------------------------------------- benchmarki
@app.get("/benchmarks", response_class=HTMLResponse)
def benchmarks_page():
    return _page("benchmarks.html")


@app.get("/api/benchmarks")
def benchmarks_data():
    return json.loads(BENCH.read_text(encoding="utf-8"))


@app.get("/api/bench_sweep")
def bench_sweep():
    """Wyniki sweepu modeli (eval/bench_models.py dopisuje je w trakcie przebiegu); null = brak wyniku."""
    path = _sweep_path()
    data = _read_json(path, None)
    mtime = path.stat().st_mtime if path.exists() else None
    if not isinstance(data, dict):
        return {"runs": [], "mtime": mtime, "missing": data is None and mtime is None}
    return {**data, "runs": [r for r in data.get("runs") or [] if isinstance(r, dict) and r.get("model")], "mtime": mtime}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"Wróbelek GUI: http://{a.host}:{a.port}")
    uvicorn.run(app, host=a.host, port=a.port)
