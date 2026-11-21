"""Web GUI: wgraj PDF -> analiza -> podgląd dokumentu obok wyodrębnionych danych, z podświetleniem źródła.

  python gui.py            # http://127.0.0.1:8000
"""
from __future__ import annotations

import io
import json
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

from o2j.pdf import _PDFIUM_LOCK, flat_page  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

DATA = ROOT / "gui_data"
app = FastAPI(title="Odwołania2JSON")
_pipes: dict[str, Pipeline] = {}
PROFILE_INFO = {
    "deterministyczny": "Reguły bez LLM — najtańszy, w pełni powtarzalny",
    "ekonomiczny": "Tani model, bez pętli naprawy",
    "standard": "Szybki model + weryfikacja i naprawa",
    "maksymalny": "Głosowanie kilku przebiegów/modeli — najwyższa jakość",
}


def get_pipe(profile: str | None = None) -> Pipeline:
    from o2j.config import load_settings
    key = profile or ""
    if key not in _pipes:
        _pipes[key] = Pipeline(load_settings(profile=profile))
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


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "o2j" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/doctypes")
def doctypes():
    return [{"name": n, "description": s.description} for n, s in get_pipe().specs.items()]


@app.get("/api/profiles")
def profiles():
    from o2j.config import load_settings
    s = load_settings()
    names = list((s.get("profiles") or {}).keys())
    return {"default": s.get("profile"), "profiles": [{"name": n, "opis": PROFILE_INFO.get(n, "")} for n in names]}


@app.post("/api/process")
async def process(files: list[UploadFile] = File(...), case: str | None = Form(None), profile: str | None = Form(None)):
    sid = case if case and case.isalnum() and len(case) <= 32 else uuid.uuid4().hex[:10]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            continue
        path = d / name
        path.write_bytes(await f.read())
        out.append(await run_in_threadpool(_one, sid, path, profile))
    if not out:
        raise HTTPException(400, "Brak plików PDF")
    return {"session": sid, "documents": out}


def _one(sid: str, path: Path, profile: str | None = None) -> dict:
    p = get_pipe(profile)
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
        "text": "\n".join(pg.get("text", "") for pg in trace.get("page_texts", []))}, ensure_ascii=False), encoding="utf-8")
    keep = ("classification", "model", "pages", "ocr_pages", "elapsed_s", "few_shot", "verification", "usage",
            "voting", "learned_examples_available", "active_profile")
    trace["active_profile"] = p.s.get("active_profile")
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


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"Odwołania2JSON GUI: http://{a.host}:{a.port}")
    uvicorn.run(app, host=a.host, port=a.port)
