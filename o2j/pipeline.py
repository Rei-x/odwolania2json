"""End-to-end: PDF -> text/OCR -> class -> LLM extraction -> normalisation -> JSON + trace."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import extract as E
from . import pdf as P
from . import tracing as T
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
        from .llm import PROVIDERS
        PROVIDERS.update(self.s.get("providers") or {})
        from .memory import LearningStore
        lp = self.s["paths"].get("learned")
        self.memory = LearningStore(lp) if lp else None
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

    def _load_traced(self, pdf_path: Path, st: T.Steps):
        """P.load inside the 'load' step, with per-page details (text layer, OCR engine/time/cost, orientation)."""
        ocr_cfg = self.s.get("ocr", {})
        ocr_log: dict[int, dict] = {}
        engine = self._ocr

        def traced_ocr(png, _eng=engine):
            t = time.time()
            with T.meter() as m:
                out = _eng(png)
            ocr_log[id(png)] = {"duration_s": round(time.time() - t, 3), "calls": m["calls"],
                                "cost_usd": round(m["cost_usd"], 6),
                                "tokens": {"prompt": m["prompt_tokens"], "completion": m["completion_tokens"]}}
            return out
        with st.step("load", "Wczytanie") as d, T.collect_notes() as notes:
            try:
                doc = P.load(pdf_path, ocr=traced_ocr if engine is not None else None,
                             min_chars=int(ocr_cfg.get("min_chars_per_page", 40)),
                             dpi=int(ocr_cfg.get("dpi", 200)), ocr_max_pages=int(ocr_cfg.get("max_pages", 4)),
                             prep=ocr_cfg.get("preprocess"), garbage_threshold=float(ocr_cfg.get("garbage_threshold", 0.1)))
                load_error = None
            except Exception as e:  # noqa: BLE001  corrupted / unreadable file
                doc, load_error = P.Document(path=pdf_path), repr(e)
            page_notes = {n["page"]: n for n in notes if n["kind"] == "page"}
            orient = [n for n in notes if n["kind"] == "orientation"]
            eng_name = type(engine).__name__ if engine is not None else None
            eng_model = getattr(engine, "model", None)
            pages, oi = [], 0
            for p in doc.pages:
                info = {k: v for k, v in (page_notes.get(p.number) or {}).items() if k not in ("kind", "page")}
                info.update(page=p.number, source=p.source, chars=len(p.text), preview=T.preview(p.text, 400))
                if p.source == "ocr":
                    if oi < len(orient):  # preprocessing notes come in the order of the rendered (OCR) pages
                        info["orientation"] = {k: v for k, v in orient[oi].items() if k != "kind"}
                        oi += 1
                    info["ocr"] = {"engine": eng_name, "model": eng_model, **(ocr_log.get(id(p.image)) or {})}
                pages.append(info)
            d.update(pages=pages, n_pages=len(doc.pages), ocr_pages=[p.number for p in doc.pages if p.source == "ocr"],
                     preprocess=ocr_cfg.get("preprocess") or [], ocr_engine=eng_name, ocr_model=eng_model,
                     load_error=load_error)
        return doc, load_error

    @staticmethod
    def _finish(trace: dict, st: T.Steps) -> dict:
        trace["steps"] = st.items
        trace["steps_summary"] = st.summary()
        return trace

    def process(self, pdf_path: Path, exclude_cases: set[str] = frozenset()) -> tuple[str, dict, dict]:
        st = T.Steps(time.time())
        try:
            return self._process(pdf_path, exclude_cases, st)
        except Exception as e:  # keep the steps recorded so far (e.g. OCR failed) for the processing trace
            try:
                e.trace_steps, e.trace_steps_summary = st.items, st.summary()
            except Exception:  # noqa: BLE001  (exception types that refuse attributes)
                pass
            raise

    def _process(self, pdf_path: Path, exclude_cases: set[str], st: T.Steps) -> tuple[str, dict, dict]:
        t0 = st.t0
        ocr_cfg = self.s.get("ocr", {})
        doc, load_error = self._load_traced(pdf_path, st)
        full = doc.text()
        if self.mode == "deterministic":
            return self._process_deterministic(pdf_path, doc, full, load_error, t0, st)
        ccfg = self.s.get("classification", {})
        with st.step("classify", "Klasyfikacja") as cd:
            doctype, cls_info = classify(full, pdf_path, self.specs, self.llm,
                                         float(ccfg.get("min_score", 3)),
                                         ccfg.get("mode", "llm_confirm"),
                                         model=ccfg.get("model"),
                                         vote_models=ccfg.get("vote_models"),
                                         use_filename=bool(ccfg.get("use_filename", False)))
            cd.update(self._cls_detail(full, doctype, cls_info, float(ccfg.get("min_score", 3))))
        trace = {"file": str(pdf_path), "doctype": doctype, "classification": cls_info, "load_error": load_error,
                 "pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"]}
        if doctype not in self.specs:
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, {}, self._finish(trace, st)
        spec = self.specs[doctype]
        text = doc.text(spec.pages)
        if not text.strip():  # nothing readable -> schema-valid skeleton (nulls still score as TN)
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, spec.skeleton(), self._finish(trace, st)
        with st.step("few_shot", "Przykłady (few-shot)") as fd:
            learned = self.memory.example_dirs(doctype) if self.memory else []
            sim_scores: list = []
            ex_names: list = []
            examples = E.few_shot_examples(spec, self.s["paths"].get("train"), text, set(exclude_cases), spec.few_shot,
                                           learned=learned, scores_out=sim_scores, names_out=ex_names)
            fd.update(k=spec.few_shot, learned_available=len(learned),
                      examples=[{"name": n, "similarity": s, "learned": str(n).startswith("learned:")}
                                for n, s in zip(ex_names, sim_scores)])
        trace["nearest_example_similarity"] = sim_scores[0] if sim_scores else None
        trace["learned_examples_available"] = len(learned)
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
        vcfg = self.s.get("voting") or {}
        n_votes = int(vcfg.get("n", 1) or 1)
        with st.step("extract", "Ekstrakcja") as xd:
            xd.update(prompt_chars={"system": len(system), "user": len(user)},
                      prompt_tokens_est=(len(system) + len(user)) // 4, images=len(images or []),
                      few_shot=len(examples))
            if n_votes > 1:  # several independent extractions (models and/or sampled runs), field-level vote
                from concurrent.futures import ThreadPoolExecutor as _TPE

                from .voting import vote
                models = vcfg.get("models") or [self.llm.model]

                def _run(i):
                    m = models[i % len(models)]
                    temp = 0 if i < len(models) else float(vcfg.get("temperature", 0.7))
                    r, mt = self.llm.extract_json(system, user, spec.json_schema(), name=doctype, images=images,
                                                  model=m, temperature=temp)
                    return E.postprocess(spec, r), mt
                with _TPE(max_workers=n_votes) as ex:
                    runs = list(ex.map(T.bind(_run), range(n_votes)))
                voters = [r for r, _ in runs]
                if vcfg.get("include_deterministic"):  # YAML rules as an extra (tie-breaking) voter
                    try:
                        from . import deterministic as D
                        if D.has_rules(spec):
                            n = D.pages_to_read(spec)
                            voters.append(E.postprocess(spec, D.extract(spec, [p.text for p in (doc.pages[:n] if n else doc.pages)])))
                    except Exception as e:  # noqa: BLE001
                        trace["voting_det_error"] = repr(e)
                result, vote_info = vote(voters, doc)
                raw, meta = result, runs[0][1]
                vote_info["models"] = [models[i % len(models)] for i in range(n_votes)]
                trace["voting"] = vote_info
                xd.update(voting=vote_info, raw_outputs=[{"model": mt.get("model"), "raw": mt.get("raw")} for _, mt in runs])
            else:
                raw, meta = self.llm.extract_json(system, user, spec.json_schema(), name=doctype, images=images)
                result = E.postprocess(spec, raw)
            first_raw, first_result = raw, result
            retries = 0
            while E.fill_ratio(result) < 0.25 and len(text) > 300 and retries < 2:  # suspiciously empty -> retry
                retries += 1
                raw, meta = self.llm.extract_json(system, user, spec.json_schema(), name=doctype, images=images)
                cand = E.postprocess(spec, raw)
                if E.fill_ratio(cand) > E.fill_ratio(result):
                    result = cand
            trace["extraction_retries"] = retries
            xd.update(model=meta.get("model"), attempts=meta.get("attempts"), retries=retries,
                      raw_output=first_raw if n_votes > 1 else raw, raw_text=T.preview(meta.get("raw"), 20000),
                      fill_ratio=round(E.fill_ratio(result), 3))
        # small-model safety net: snap copy errors to the document text, let rules fill empty fields
        pcfg = self.s.get("postprocess") or {}
        with st.step("normalize", "Normalizacja") as nd:
            if n_votes <= 1:  # raw model JSON -> schema normalisation (dates, NIP digits, names in nominative ...)
                nd["normalized"] = self._norm_diff(first_raw, first_result)
            if pcfg.get("snap_to_text", True):
                trace["snap_to_text"] = E.snap_to_text(spec, result, doc)
                nd["snap_to_text"] = trace["snap_to_text"]
            if pcfg.get("rules_fill", True):
                try:
                    from . import deterministic as D
                    if D.has_rules(spec):
                        n = D.pages_to_read(spec)
                        det0 = E.postprocess(spec, D.extract(spec, [p.text for p in (doc.pages[:n] if n else doc.pages)]))
                        trace["rules_fill"] = E.rules_fill(spec, result, det0, doc)
                        nd["rules_fill"] = trace["rules_fill"]
                except Exception as e:  # noqa: BLE001
                    trace["rules_fill_error"] = repr(e)
                    nd["rules_fill_error"] = repr(e)
        # agentic verify -> repair loop
        derived = E.derived_fields(spec)
        with st.step("ground", "Dowody") as gd:
            evidence = E.ground(doc, result, derived)
        rounds = []
        with st.step("verify", "Weryfikacja i naprawa") as vd:
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
            remaining = V.verify(spec, result, evidence, ocr_doc=bool(images))
            trace["verification"] = {"rounds": rounds, "remaining_issues": remaining}
            vd.update(max_rounds=int(self.s.get("verify", {}).get("max_rounds", 2)), rounds=rounds,
                      remaining_issues=remaining)
        rcfg = self.s.get("router") or {}
        if rcfg.get("enabled"):  # adaptive escalation of hard documents
            with st.step("router", "Router") as rd:
                from . import deterministic as D
                from . import router as R
                det = None
                try:
                    if D.has_rules(spec):
                        n = D.pages_to_read(spec)
                        det = E.postprocess(spec, D.extract(spec, [p.text for p in (doc.pages[:n] if n else doc.pages)]))
                except Exception as e:  # noqa: BLE001
                    trace["router_det_error"] = repr(e)
                sim = trace.get("nearest_example_similarity")
                diff = R.difficulty(result, det, remaining, bool(trace.get("ocr_pages")),
                                    None if sim is None else max(0.0, 100.0 - sim), rcfg)
                trace["router"] = diff
                if diff["escalate"]:
                    new, vinfo = R.escalate(self, spec, system, user, images, doc, result, det, rcfg)
                    trace["router"]["changes"] = R.changed_fields(result, new)
                    trace["router"]["vote"] = vinfo
                    result = new
                    evidence = E.ground(doc, result, derived)
                rd.update(trace["router"])
        gd.update(self._ground_detail(evidence))
        trace.update(model=meta["model"], usage=meta["usage"], few_shot=len(examples),
                     raw_llm_output=raw, evidence=evidence,
                     page_texts=[{"page": p.number, "source": p.source, "text": p.text} for p in doc.pages],
                     elapsed_s=round(time.time() - t0, 2))
        return doctype, result, self._finish(trace, st)

    def _cls_detail(self, full: str, doctype: str, cls_info: dict, min_score: float) -> dict:
        from .classify import rule_matches
        try:
            matched = rule_matches(full[:6000], self.specs)
        except Exception:  # noqa: BLE001
            matched = {}
        return {"decision": doctype, "out_of_scope": doctype not in self.specs, "min_score": min_score,
                "method": cls_info.get("method"), "confident": cls_info.get("confident"),
                "scores": cls_info.get("scores"), "matched_keywords": matched,
                "llm_votes": cls_info.get("votes"), "llm_choice": cls_info.get("llm_choice"),
                "llm_errors": cls_info.get("llm_errors"), "margin": cls_info.get("margin")}

    @staticmethod
    def _norm_diff(raw: dict, result: dict) -> list[dict]:
        from .memory import diff
        try:
            return [c for c in diff(raw if isinstance(raw, dict) else {}, result) if c["before"] != c["after"]][:200]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _ground_detail(evidence: list[dict]) -> dict:
        by = {}
        for e in evidence or []:
            by[e.get("method") or "?"] = by.get(e.get("method") or "?", 0) + 1
        return {"counts": by, "fields": [{k: e.get(k) for k in ("field", "method", "page", "quote") if e.get(k) is not None}
                                         for e in evidence or []]}

    def _process_deterministic(self, pdf_path: Path, doc, full: str, load_error, t0: float,
                               st: T.Steps | None = None) -> tuple[str, dict, dict]:
        """Rules-only classification + YAML-driven extraction (o2j.deterministic); never calls an LLM."""
        from . import deterministic as D
        st = st or T.Steps(t0)
        cls = self.s.get("classification", {})
        with st.step("classify", "Klasyfikacja") as cd:
            doctype, cls_info = D.classify(full, pdf_path.name, self.specs, float(cls.get("min_score", 3)),
                                           float(cls.get("min_margin", 2)))
            cd.update(self._cls_detail(full, doctype, cls_info, float(cls.get("min_score", 3))))
        trace = {"file": str(pdf_path), "doctype": doctype, "classification": cls_info, "load_error": load_error,
                 "pages": len(doc.pages), "ocr_pages": [p.number for p in doc.pages if p.source == "ocr"],
                 "mode": "deterministic"}
        if doctype not in self.specs:
            trace["elapsed_s"] = round(time.time() - t0, 2)
            return doctype, {}, self._finish(trace, st)
        spec = self.specs[doctype]
        n = D.pages_to_read(spec)
        pages = [p.text for p in (doc.pages[:n] if n else doc.pages)]
        raw = None
        with st.step("extract", "Ekstrakcja (reguły)", model="deterministic") as xd:
            if not "".join(pages).strip() or not D.has_rules(spec):
                result = spec.skeleton()
                xd["skipped"] = "brak tekstu" if not "".join(pages).strip() else "brak reguł dla typu"
            else:
                raw = D.extract(spec, pages)
                xd.update(raw_output=raw, pages_read=len(pages))
        if raw is not None:
            with st.step("normalize", "Normalizacja") as nd:
                result = E.postprocess(spec, raw)
                trace["raw_output"] = raw
                nd["normalized"] = self._norm_diff(raw, result)
        with st.step("ground", "Dowody") as gd:
            evidence = E.ground(doc, result, E.derived_fields(spec))
            gd.update(self._ground_detail(evidence))
        trace.update(model="deterministic", evidence=evidence,
                     page_texts=[{"page": p.number, "source": p.source, "text": p.text} for p in doc.pages],
                     elapsed_s=round(time.time() - t0, 2))
        return doctype, result, self._finish(trace, st)

    def fallback(self, path: Path) -> tuple[str, dict]:
        """Best-effort doctype from filename (+text if readable) and a null skeleton."""
        from .classify import rule_scores
        try:
            text = P.load(path).text()[:6000]
        except Exception:  # noqa: BLE001
            text = ""
        scores = sorted(rule_scores(text, path.name, self.specs).items(), key=lambda x: -x[1])
        (name, score), second = scores[0], (scores[1][1] if len(scores) > 1 else 0)
        min_score = float(self.s.get("classification", {}).get("min_score", 3))
        confident = score >= min_score and score - second >= 2  # only a confident class gets a skeleton
        return (name, self.specs[name].skeleton()) if confident else ("inny", {})

    def run_dir(self, input_dir: Path, output_dir: Path, trace_dir: Path | None = None, workers: int = 8,
                exclude_self: bool = False, log=print) -> list[dict]:
        pdfs = sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in P.SUPPORTED_EXT
                      and not p.name.startswith("."))
        done: list[dict] = []

        def job(p: Path):
            rel = p.relative_to(input_dir).with_suffix(".json")
            excl = {p.parent.name} if exclude_self else set()
            try:
                doctype, result, trace = self.process(p, excl)
                err = None
            except Exception as e:  # noqa: BLE001  never leave a document without output
                doctype, result = self.fallback(p)
                trace, err = {"file": str(p), "error": repr(e), "doctype": doctype}, repr(e)
            return {"rel": rel, "doctype": doctype, "result": result, "trace": trace, "error": err,
                    "matched": doctype in self.specs}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(job, p) for p in pdfs]
            for f in as_completed(futs):
                r = f.result()
                done.append(r)
                log(f"[{len(done)}/{len(pdfs)}] {r['rel']} -> {r['doctype'] if r['matched'] else 'NIEDOPASOWANY'}"
                    + (f"  ERROR {r['error']}" if r["error"] else f"  ({r['trace'].get('elapsed_s')}s)"))

        # case level: documents in the same folder form one case (cross-checks + safe cross-fill)
        from .case import analyze_case, load_case_rules
        rules = load_case_rules(self.s["paths"]["doctypes"].parent / "case.yaml")
        cases: dict[Path, list[dict]] = {}
        for r in done:
            cases.setdefault(r["rel"].parent, []).append(r)
        for case_rel, docs in cases.items():
            matched = [d for d in docs if d["matched"]]
            if rules and len({d["doctype"] for d in matched}) > 1:
                case_docs = {d["rel"].name: {"doctype": d["doctype"], "result": d["result"],
                                             "text": "\n".join(p.get("text", "") for p in d["trace"].get("page_texts", []))}
                             for d in matched}
                report = analyze_case(case_docs, rules)
                for ch in report["uzupelnienia_krzyzowe"]:
                    d = next(x for x in matched if x["rel"].name == ch["dokument"])
                    d["trace"].setdefault("cross_fill", []).append(ch)
                if trace_dir:
                    cp = trace_dir / case_rel / "_sprawa.json"
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(E.dumps(report), encoding="utf-8")

        summary = []
        for r in done:
            out = output_dir / r["rel"]
            out.parent.mkdir(parents=True, exist_ok=True)
            if r["matched"]:
                out.write_text(E.dumps(r["result"]), encoding="utf-8")
            else:  # per UZP: out-of-scope document -> file containing only {}
                out.write_text("{}", encoding="utf-8")
                r["trace"]["unmatched"] = "Nie udało się dopasować typu dokumentu — zapisano pusty JSON {}."
            if trace_dir:
                tr = trace_dir / r["rel"].with_suffix(".trace.json")
                tr.parent.mkdir(parents=True, exist_ok=True)
                tr.write_text(E.dumps(r["trace"]), encoding="utf-8")
            summary.append({"file": str(r["rel"]), "doctype": r["doctype"] if r["matched"] else "NIEDOPASOWANY",
                            "error": r["error"], "elapsed_s": r["trace"].get("elapsed_s")})
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
