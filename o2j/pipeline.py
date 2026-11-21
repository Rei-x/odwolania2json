"""End-to-end: PDF -> text/OCR -> class -> LLM extraction -> normalisation -> JSON + trace."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import extract as E
from . import pdf as P
from . import verify as V
from .classify import classify
from .config import load_settings
from .llm import LLM
from .spec import load_specs


class Pipeline:
    def __init__(self, settings: dict | None = None, model: str | None = None, mode: str | None = None):
        self.s = settings or load_settings()
        if mode:
            self.s.setdefault("extraction", {})["mode"] = mode
        if model:
            self.s["llm"]["model"] = model
        self.specs = load_specs(self.s["paths"]["doctypes"])
        ext = self.s.get("extraction") or {}
        self.mode = ext.get("mode", "llm")
        ocr_cfg = self.s.get("ocr", {})
        from .ocr import make_engine
        if self.mode == "deterministic":
            # no LLM client at all; OCR only with an explicitly configured local engine (default: none)
            self.llm = None
            self.model_name = "deterministic"
            self._ocr = make_engine({**ocr_cfg, "engine": ext.get("ocr_engine", "none")}, self.s["llm"])
        else:
            self.llm = LLM(self.s["llm"])
            self.model_name = self.llm.model
            self._ocr = make_engine(ocr_cfg, self.s["llm"])

    def process(self, pdf_path: Path, exclude_cases: set[str] = frozenset()) -> tuple[str, dict, dict]:
        t0 = time.time()
        ocr_cfg = self.s.get("ocr", {})
        try:
            doc = P.load(pdf_path, ocr=self._ocr, min_chars=int(ocr_cfg.get("min_chars_per_page", 40)),
                     dpi=int(ocr_cfg.get("dpi", 200)), ocr_max_pages=int(ocr_cfg.get("max_pages", 4)), prep=ocr_cfg.get("preprocess"))
            load_error = None
        except Exception as e:  # noqa: BLE001  corrupted / unreadable file
            doc, load_error = P.Document(path=pdf_path), repr(e)
        full = doc.text()
        if self.mode == "deterministic":
            return self._process_deterministic(pdf_path, doc, full, load_error, t0)
        doctype, cls_info = classify(full, pdf_path, self.specs, self.llm,
                                     float(self.s.get("classification", {}).get("min_score", 3)),
                                     self.s.get("classification", {}).get("mode", "llm_confirm"))
        trace = {"file": str(pdf_path), "doctype": doctype, "classification": cls_info, "load_error": load_error,
                 "pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"]}
        if doctype not in self.specs:
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, {}, trace
        spec = self.specs[doctype]
        text = doc.text(spec.pages)
        if not text.strip():  # nothing readable -> schema-valid skeleton (nulls still score as TN)
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, spec.skeleton(), trace
        examples = E.few_shot_examples(spec, self.s["paths"].get("train"), text, set(exclude_cases), spec.few_shot)
        system, user = E.build_prompt(spec, text, examples)
        images = None
        if ocr_cfg.get("attach_images", True):
            images = [p.image for p in doc.pages[: spec.pages or len(doc.pages)] if p.source == "ocr" and p.image]
            if images:
                user += ("\n\nUWAGA: tekst dokumentu pochodzi z OCR skanu i może zawierać błędy odczytu. "
                         "Dołączono obrazy stron — w razie wątpliwości (cyfry, nazwiska, polskie znaki) rozstrzygaj na podstawie obrazu.")
        want = spec.raw.get("page_images") or []
        if want and not images and doc.pages:
            idx = sorted({len(doc.pages) - 1 if w == "last" else int(w) - 1 for w in want if str(w) == "last" or str(w).isdigit()})
            images = [P.render_page_png(pdf_path, i) for i in idx if 0 <= i < len(doc.pages)]
            images = [im for im in images if im]
            if images:
                user += ("\n\nDołączono obraz strony dokumentu (np. z graficznym podpisem). Odczytuj z niego tylko to, "
                         "czego brakuje w tekście (np. nazwiska podpisujących); nie zgaduj nieczytelnych podpisów.")
        trace["images_attached"] = len(images or [])
        raw, meta = self.llm.extract_json(system, user, spec.json_schema(), name=doctype, images=images)
        result = E.postprocess(spec, raw)
        retries = 0
        while E.fill_ratio(result) < 0.25 and len(text) > 300 and retries < 2:  # suspiciously empty -> retry
            retries += 1
            raw, meta = self.llm.extract_json(system, user, spec.json_schema(), name=doctype, images=images)
            cand = E.postprocess(spec, raw)
            if E.fill_ratio(cand) > E.fill_ratio(result):
                result = cand
        trace["extraction_retries"] = retries
        # agentic verify -> repair loop
        derived = E.derived_fields(spec)
        evidence = E.ground(doc, result, derived)
        rounds = []
        for _ in range(int(self.s.get("verify", {}).get("max_rounds", 2))):
            issues = V.verify(spec, result, evidence, ocr_doc=bool(images))
            if not issues:
                break
            try:
                result, changes = V.repair(self.llm, spec, text, result, issues, images=images)
            except Exception as e:  # noqa: BLE001
                rounds.append({"issues": issues, "error": repr(e)})
                break
            evidence = E.ground(doc, result, derived)
            rounds.append({"issues": issues, "changes": changes})
            if not changes:
                break
        trace["verification"] = {"rounds": rounds, "remaining_issues": V.verify(spec, result, evidence, ocr_doc=bool(images))}
        trace.update(model=meta["model"], usage=meta["usage"], few_shot=len(examples),
                     raw_llm_output=raw, evidence=evidence,
                     page_texts=[{"page": p.number, "source": p.source, "text": p.text} for p in doc.pages],
                     elapsed_s=round(time.time() - t0, 2))
        return doctype, result, trace

    def _process_deterministic(self, pdf_path: Path, doc, full: str, load_error, t0: float) -> tuple[str, dict, dict]:
        """Rules-only classification + YAML-driven extraction (o2j.deterministic); never calls an LLM."""
        from . import deterministic as D
        cls = self.s.get("classification", {})
        doctype, cls_info = D.classify(full, pdf_path.name, self.specs, float(cls.get("min_score", 3)),
                                       float(cls.get("min_margin", 2)))
        trace = {"file": str(pdf_path), "doctype": doctype, "classification": cls_info, "load_error": load_error,
                 "pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"],
                 "mode": "deterministic"}
        if doctype not in self.specs:
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, {}, trace
        spec = self.specs[doctype]
        n = D.pages_to_read(spec)
        pages = [p.text for p in (doc.pages[:n] if n else doc.pages)]
        if not "".join(pages).strip() or not D.has_rules(spec):
            result = spec.skeleton()
        else:
            raw = D.extract(spec, pages)
            result = E.postprocess(spec, raw)
            trace["raw_output"] = raw
        trace.update(model="deterministic", evidence=E.ground(doc, result, E.derived_fields(spec)),
                     page_texts=[{"page": p.number, "source": p.source, "text": p.text} for p in doc.pages],
                     elapsed_s=round(time.time() - t0, 2))
        return doctype, result, trace

    def fallback(self, path: Path) -> tuple[str, dict]:
        """Best-effort doctype from filename (+text if readable) and a null skeleton."""
        from .classify import rule_scores
        try:
            text = P.load(path).text()[:6000]
        except Exception:  # noqa: BLE001
            text = ""
        scores = rule_scores(text, path.name, self.specs)
        name, score = max(scores.items(), key=lambda x: x[1])
        return (name, self.specs[name].skeleton()) if score > 0 else ("inny", {})

    def run_dir(self, input_dir: Path, output_dir: Path, trace_dir: Path | None = None, workers: int = 8,
                exclude_self: bool = False, log=print) -> list[dict]:
        pdfs = sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in P.SUPPORTED_EXT
                      and not p.name.startswith("."))
        summary = []

        def job(p: Path):
            rel = p.relative_to(input_dir).with_suffix(".json")
            excl = {p.parent.name} if exclude_self else set()
            try:
                doctype, result, trace = self.process(p, excl)
                err = None
            except Exception as e:  # noqa: BLE001  never leave a document without output
                doctype, result = self.fallback(p)
                trace, err = {"file": str(p), "error": repr(e), "doctype": doctype}, repr(e)
            out = output_dir / rel
            matched = doctype in self.specs
            out.parent.mkdir(parents=True, exist_ok=True)
            if matched:
                out.write_text(E.dumps(result), encoding="utf-8")
            else:  # per UZP: out-of-scope document -> file containing only {}
                out.write_text("{}", encoding="utf-8")
                trace["unmatched"] = "Nie udało się dopasować typu dokumentu — zapisano pusty JSON {}."
            if trace_dir:
                tr = trace_dir / rel.with_suffix(".trace.json")
                tr.parent.mkdir(parents=True, exist_ok=True)
                tr.write_text(E.dumps(trace), encoding="utf-8")
            return {"file": str(rel), "doctype": doctype if matched else "NIEDOPASOWANY", "error": err,
                    "elapsed_s": trace.get("elapsed_s")}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(job, p) for p in pdfs]
            for f in as_completed(futs):
                r = f.result()
                summary.append(r)
                log(f"[{len(summary)}/{len(pdfs)}] {r['file']} -> {r['doctype']}"
                    + (f"  ERROR {r['error']}" if r["error"] else f"  ({r['elapsed_s']}s)"))
        return summary


def build_gt(train_dir: Path, specs, gt_dir: Path, cases: list[str] | None = None):
    """Map each training PDF to its reference JSON (per doctype `examples`) under the PDF's stem.
    PDFs without a reference (out-of-scope documents) expect an empty JSON {}."""
    for case in sorted(train_dir.iterdir()):
        if not case.is_dir() or (cases and case.name not in cases):
            continue
        mapped = set()
        for spec in specs.values():
            v = (spec.raw.get("examples") or {}).get("pdf")
            mapped |= set(v if isinstance(v, list) else [v])
        for pdf in case.glob("*.pdf"):
            if pdf.name not in mapped:
                out = gt_dir / case.name / (pdf.stem + ".json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("{}", encoding="utf-8")
        for spec in specs.values():
            ex = spec.raw.get("examples") or {}
            names = ex.get("pdf") if isinstance(ex.get("pdf"), list) else [ex.get("pdf", "_")]
            pdf = next((case / n for n in names if (case / n).exists()), case / "_")
            js = case / ex.get("json", "_")
            if pdf.exists() and js.exists():
                out = gt_dir / case.name / (pdf.stem + ".json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(js.read_text(encoding="utf-8"), encoding="utf-8")
