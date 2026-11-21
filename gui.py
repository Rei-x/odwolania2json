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
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, Response  # noqa: E402

from o2j.pdf import _PDFIUM_LOCK  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

DATA = ROOT / "gui_data"
app = FastAPI(title="Odwołania2JSON")
_pipe: Pipeline | None = None


def get_pipe() -> Pipeline:
    global _pipe
    if _pipe is None:
        _pipe = Pipeline()
    return _pipe


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
                page = pdf[n]
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


@app.post("/api/process")
async def process(files: list[UploadFile] = File(...)):
    sid = uuid.uuid4().hex[:10]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            continue
        path = d / name
        path.write_bytes(await f.read())
        out.append(await run_in_threadpool(_one, sid, path))
    if not out:
        raise HTTPException(400, "Brak plików PDF")
    return {"session": sid, "documents": out}


def _one(sid: str, path: Path) -> dict:
    p = get_pipe()
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
    keep = ("classification", "model", "pages", "ocr_pages", "elapsed_s", "few_shot", "verification", "usage")
    return {"session": sid, "file": path.name, "doctype": doctype, "result": result,
            "trace": {**{k: trace.get(k) for k in keep}, "evidence": evidence}}


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
