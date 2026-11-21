"""Web GUI: wgraj PDF -> analiza -> podgląd PDF obok wyodrębnionego JSON z dowodami.

  python gui.py            # http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402

from o2j.pipeline import Pipeline  # noqa: E402

DATA = ROOT / "gui_data"
app = FastAPI(title="Odwołania2JSON")
pipe: Pipeline | None = None


def get_pipe() -> Pipeline:
    global pipe
    if pipe is None:
        pipe = Pipeline()
    return pipe


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "o2j" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/doctypes")
def doctypes():
    p = get_pipe()
    return [{"name": n, "description": s.description, "fields": s.field_guide()} for n, s in p.specs.items()]


@app.post("/api/process")
async def process(files: list[UploadFile] = File(...)):
    sid = uuid.uuid4().hex[:10]
    d = DATA / sid
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in files:
        name = Path(f.filename or "dokument.pdf").name
        if not name.lower().endswith(".pdf"):
            continue
        out = d / name
        out.write_bytes(await f.read())
        paths.append(out)
    if not paths:
        raise HTTPException(400, "Brak plików PDF")
    p = get_pipe()

    def one(path: Path):
        try:
            doctype, result, trace = p.process(path)
        except Exception as e:  # noqa: BLE001
            return {"file": path.name, "doctype": "error", "error": str(e), "result": {}, "trace": {}}
        (d / (path.stem + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"file": path.name, "doctype": doctype, "result": result,
                "trace": {k: trace.get(k) for k in ("classification", "evidence", "model", "pages", "ocr_pages", "elapsed_s", "few_shot")}}

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, paths))
    return {"session": sid, "documents": results}


@app.get("/files/{sid}/{name}")
def files(sid: str, name: str):
    path = (DATA / sid / name).resolve()
    if DATA.resolve() not in path.parents or not path.exists():
        raise HTTPException(404)
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
