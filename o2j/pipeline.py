"""End-to-end: PDF -> text/OCR -> class -> LLM extraction -> normalisation -> JSON + trace."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import extract as E
from . import pdf as P
from .classify import classify
from .config import load_settings
from .llm import LLM
from .spec import load_specs


class Pipeline:
    def __init__(self, settings: dict | None = None, model: str | None = None):
        self.s = settings or load_settings()
        if model:
            self.s["llm"]["model"] = model
        self.specs = load_specs(self.s["paths"]["doctypes"])
        self.llm = LLM(self.s["llm"])
        ocr_cfg = self.s.get("ocr", {})
        self._ocr = None
        if ocr_cfg.get("engine") == "vlm":
            self._ocr = lambda png: self.llm.ocr(png, model=ocr_cfg.get("model") or None)

    def process(self, pdf_path: Path, exclude_cases: set[str] = frozenset()) -> tuple[str, dict, dict]:
        t0 = time.time()
        ocr_cfg = self.s.get("ocr", {})
        doc = P.load(pdf_path, ocr=self._ocr, min_chars=int(ocr_cfg.get("min_chars_per_page", 40)),
                     dpi=int(ocr_cfg.get("dpi", 200)), ocr_max_pages=int(ocr_cfg.get("max_pages", 4)))
        full = doc.text()
        doctype, cls_info = classify(full, pdf_path, self.specs, self.llm,
                                     float(self.s.get("classification", {}).get("min_score", 3)))
        trace = {"file": str(pdf_path), "doctype": doctype, "classification": cls_info,
                 "pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"]}
        if doctype not in self.specs:
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, {}, trace
        spec = self.specs[doctype]
        text = doc.text(spec.pages)
        examples = E.few_shot_examples(spec, self.s["paths"].get("train"), text, set(exclude_cases), spec.few_shot)
        system, user = E.build_prompt(spec, text, examples)
        raw, meta = self.llm.extract_json(system, user, spec.json_schema(), name=doctype)
        result = E.postprocess(spec, raw)
        trace.update(model=meta["model"], usage=meta["usage"], few_shot=len(examples),
                     raw_llm_output=raw, evidence=E.ground(doc, result, E.derived_fields(spec)),
                     elapsed_s=round(time.time() - t0, 2))
        return doctype, result, trace

    def run_dir(self, input_dir: Path, output_dir: Path, trace_dir: Path | None = None, workers: int = 8,
                exclude_self: bool = False, log=print) -> list[dict]:
        pdfs = sorted(p for p in input_dir.rglob("*") if p.suffix.lower() == ".pdf")
        summary = []

        def job(p: Path):
            rel = p.relative_to(input_dir).with_suffix(".json")
            excl = {p.parent.name} if exclude_self else set()
            try:
                doctype, result, trace = self.process(p, excl)
                err = None
            except Exception as e:  # noqa: BLE001
                doctype, result, trace, err = "error", {}, {"file": str(p), "error": repr(e)}, repr(e)
            out = output_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(E.dumps(result), encoding="utf-8")
            if trace_dir:
                tr = trace_dir / rel.with_suffix(".trace.json")
                tr.parent.mkdir(parents=True, exist_ok=True)
                tr.write_text(E.dumps(trace), encoding="utf-8")
            return {"file": str(rel), "doctype": doctype, "error": err, "elapsed_s": trace.get("elapsed_s")}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(job, p) for p in pdfs]
            for f in as_completed(futs):
                r = f.result()
                summary.append(r)
                log(f"[{len(summary)}/{len(pdfs)}] {r['file']} -> {r['doctype']}"
                    + (f"  ERROR {r['error']}" if r["error"] else f"  ({r['elapsed_s']}s)"))
        return summary


def build_gt(train_dir: Path, specs, gt_dir: Path, cases: list[str] | None = None):
    """Map each training PDF to its reference JSON (per doctype `examples`) under the PDF's stem."""
    for case in sorted(train_dir.iterdir()):
        if not case.is_dir() or (cases and case.name not in cases):
            continue
        for spec in specs.values():
            ex = spec.raw.get("examples") or {}
            pdf, js = case / ex.get("pdf", "_"), case / ex.get("json", "_")
            if pdf.exists() and js.exists():
                out = gt_dir / case.name / (Path(ex["pdf"]).stem + ".json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(js.read_text(encoding="utf-8"), encoding="utf-8")
