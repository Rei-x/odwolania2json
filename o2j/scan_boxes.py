"""Evidence boxes on scanned pages, for the GUI only.

A scan has no PDF text layer: its text comes from the VLM OCR (o2j/ocr.py), which returns no coordinates, so the
GUI could show the quote but not where it is on the page. Here a local text detector + recogniser (RapidOCR:
PP-OCRv6 small det + rec, multilingual incl. Polish, ONNX on CPU, Apache-2.0) reads the rendered page once and
returns word boxes with rough text. A field's quote is then fuzzy-matched to those words (diacritics folded, spaces and punctuation
ignored, so it may span several lines) and the matched words become `rects`, the same page-relative percentages
the text-layer path produces.

- Optional dependency (requirements-gui.txt). Without `rapidocr` available() is False and scans keep only the quote.
  Both models ship inside the rapidocr wheel (~31 MB), so nothing is downloaded at runtime.
- Imported lazily by gui.py; the CLI pipeline (run.py) never imports this module.
- Pages turned by 90/180/270 degrees: the page is read upright (PP-LCNet doc_ori, o2j/orientation.py) and the
  boxes are mapped back onto the page as rendered, which is what the GUI shows (/api/page renders the original).
- One page at a time on a single background worker (bounded CPU and memory); models load once, on first use.
  Results are cached per (document, page) in memory and next to the PDF (.<stem>.p<n>.words.json).
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import unicodedata
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

VERSION = 2            # bump when the OCR settings change, so cached word boxes are recomputed
RENDER_SIDE = 2000     # px, long side of the page render that is recognised (A4 ~ 170 dpi)
DET_SIDE = 960         # px, long side of the copy the text detector sees (memory scales with its area)
MIN_SCORE = 80.0       # same bar as o2j.extract.ground
ORIENT_MIN_PROB = 0.6  # same as o2j.orientation.correct

_AVAILABLE: bool | None = None
_ENGINE = None
_ENGINE_LOCK = threading.Lock()
_POOL: ThreadPoolExecutor | None = None
_JOBS: dict[tuple[str, int], Future] = {}
_CACHE: OrderedDict[tuple[str, int], dict] = OrderedDict()
_STATE_LOCK = threading.Lock()
_CACHE_MAX = 64


def available() -> bool:
    """True when the optional recogniser is installed (checked without importing it)."""
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            _AVAILABLE = importlib.util.find_spec("rapidocr") is not None
        except (ImportError, ValueError):
            _AVAILABLE = False
    return _AVAILABLE


# ---------------------------------------------------------------- matching (pure, no OCR needed)
def fold(s: str) -> str:
    """Lower case, Polish diacritics folded (ł -> l, ą -> a ...), everything but letters and digits dropped."""
    s = unicodedata.normalize("NFKD", s.replace("ł", "l").replace("Ł", "L"))
    return "".join(c for c in s.lower() if c.isalnum())


def _index(words: list[dict]) -> tuple[str, list[int], list[int]]:
    """Folded page string in reading order + for every char: owning word and position in the word's raw text."""
    chars, owner, pos = [], [], []
    for wi, w in enumerate(words):
        for ri, ch in enumerate(w["t"]):
            for c in fold(ch):
                chars.append(c)
                owner.append(wi)
                pos.append(ri)
    return "".join(chars), owner, pos


def _align(q: str, page: str, lo: int, hi: int) -> tuple[float, int, int] | None:
    if hi <= lo:
        return None
    al = fuzz.partial_ratio_alignment(q, page[lo:hi])
    return (al.score, lo + al.dest_start, lo + al.dest_end) if al else None


def _unrotate(box: list[float], angle: int) -> list[float]:
    """Box (x0, y0, x1, y1, fractions) on the upright image -> on the page as rendered. The upright image is
    PIL's rotate(angle, expand=True) of the page (counter-clockwise), as in o2j.orientation.correct."""
    x0, y0, x1, y1 = box
    if angle == 90:
        return [1 - y1, x0, 1 - y0, x1]
    if angle == 180:
        return [1 - x1, 1 - y1, 1 - x0, 1 - y0]
    if angle == 270:
        return [y0, 1 - x1, y1, 1 - x0]
    return [x0, y0, x1, y1]


def _rects(page: dict, owner: list[int], pos: list[int], s: int, e: int) -> list[list[float]]:
    """Chars s..e of the folded page string -> one box per text line (page-relative %, top-left origin)."""
    words = page["words"]
    span: dict[int, tuple[int, int]] = {}
    for i in range(s, e):
        wi, p = owner[i], pos[i]
        a, b = span.get(wi, (p, p + 1))
        span[wi] = (min(a, p), max(b, p + 1))
    lines: dict[int, list[float]] = {}
    for wi, (a, b) in span.items():
        w = words[wi]
        raw = w["t"]
        n = len(raw)
        x0, y0, x1, y1 = w["b"]
        # a partly matched word (OCR glued words together, 'PL' before an account number, a trailing comma): keep
        # only the matched part, in proportion to characters; a single unmatched letter/digit (an OCR slip at the
        # edge of the alignment) is taken in
        alnum = [i for i, c in enumerate(raw) if c.isalnum()]
        if sum(1 for i in alnum if i < a) == 1:
            a = alnum[0]
        if sum(1 for i in alnum if i >= b) == 1:
            b = alnum[-1] + 1
        x0, x1 = x0 + (x1 - x0) * a / n, x0 + (x1 - x0) * b / n
        cur = lines.setdefault(w["l"], [x0, y0, x1, y1])
        cur[:] = [min(cur[0], x0), min(cur[1], y0), max(cur[2], x1), max(cur[3], y1)]
    out = []
    for k in sorted(lines):
        x0, y0, x1, y1 = _unrotate(lines[k], page.get("angle", 0))
        out.append([round(x0 * 100, 3), round(y0 * 100, 3), round((x1 - x0) * 100, 3), round((y1 - y0) * 100, 3)])
    return out


def _project(quote: str, context: str, text: str) -> tuple[int, int] | None:
    """Locate the quote through its context: align the folded context to the OCR text char by char and carry the
    quote's span across. Catches short or noisy quotes ('34,00' read as '34,09') that a direct match cannot."""
    q = fold(quote)
    if not q or quote not in context:
        return None
    # o2j.extract.ground builds context = text[a-80 : b+80]: prefer the occurrence 80 chars in (or 80 before the end)
    offs, i = [], context.find(quote)
    while i >= 0:
        offs.append(i)
        i = context.find(quote, i + 1)
    tail = len(context) - 80 - len(quote)
    off = min(offs, key=lambda o: min(abs(o - 80), abs(o - tail)))
    ctx = fold(context)
    qs = len(fold(context[:off]))
    qe = qs + len(q)
    ca = fuzz.partial_ratio_alignment(ctx, text)
    if not ca or ca.score < 75 or not ca.src_start <= qs < qe <= ca.src_end:
        return None
    src, dst = ctx[ca.src_start:ca.src_end], text[ca.dest_start:ca.dest_end]
    qs, qe = qs - ca.src_start, qe - ca.src_start

    def carry(p: int, end: bool) -> int:
        for op in Levenshtein.opcodes(src, dst):
            if op.src_start <= p < op.src_end or (end and p == op.src_end):
                if op.tag == "delete":
                    return op.dest_start
                return min(op.dest_end, op.dest_start + (p - op.src_start))
        return len(dst)
    s, e = carry(qs, False), carry(qe, True)
    if e <= s:
        return None
    got = dst[s:e]
    ok = got == q if len(q) < 3 else fuzz.ratio(q, got) >= 50
    return (ca.dest_start + s, ca.dest_start + e) if ok else None


def match(page: dict, quote: str | None, context: str | None = None, value=None,
          min_score: float = MIN_SCORE) -> list[list[float]]:
    """Boxes of `quote` (else of a text `value`) among the page's OCR words; [] when there is no confident match.

    page: {"angle": 0|90|180|270, "words": [{"t": text, "b": [x0, y0, x1, y1] fractions of the upright image,
    "l": line number}]} in reading order. `context` (the evidence text around the quote) picks the right
    occurrence when the quote appears more than once, and locates short or misread quotes through the words
    around them. Without context, short quotes (< 6 folded chars) must match exactly and under 3 chars nothing
    is boxed (too ambiguous on a page of OCR noise)."""
    if not page or not page.get("words"):
        return []
    text, owner, pos = _index(page["words"])
    ctx = fold(context or "")
    # numbers/booleans are normalised values ('34.0'), not page text: only the quote and text values are looked up
    for k, cand in enumerate((quote, value if isinstance(value, str) else None)):
        if not cand:
            continue
        q = fold(cand)
        need = min_score if len(q) >= 6 else 100.0
        best = None
        if len(q) >= 3:
            if len(ctx) > len(q) + 8:
                ca = fuzz.partial_ratio_alignment(ctx, text)
                if ca and ca.score >= 60:
                    pad = max(8, len(q) // 2)
                    best = _align(q, text, max(0, ca.dest_start - pad), min(len(text), ca.dest_end + pad))
            if best is None or best[0] < need:
                g = _align(q, text, 0, len(text))
                if g and (best is None or g[0] > best[0]):
                    best = g
            if best and best[0] >= need:
                return _rects(page, owner, pos, best[1], best[2])
        if k == 0 and context:
            span = _project(cand, context, text)
            if span:
                return _rects(page, owner, pos, *span)
    return []


# ---------------------------------------------------------------- OCR (lazy, optional)
def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr import ModelType, OCRVersion, RapidOCR  # optional: requirements-gui.txt
        _ENGINE = RapidOCR(params={
            "Global.log_level": "error",
            "Global.use_cls": False,          # the page is turned upright first; lines are then upright
            "Global.return_word_box": True,
            "Global.max_side_len": RENDER_SIDE,
            "Det.ocr_version": OCRVersion.PPOCRV6, "Det.model_type": ModelType.SMALL,
            "Det.limit_type": "max", "Det.limit_side_len": DET_SIDE,  # detection on a small copy, recognition on the full render
            "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.model_type": ModelType.SMALL,  # bundled; reads ą ę ł ó ś ż
            "EngineConfig.onnxruntime.intra_op_num_threads": min(2, os.cpu_count() or 1),
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
    return _ENGINE


def read_image(im) -> dict:
    """PIL image of a page -> {"angle", "words"} (see match). Runs the recogniser; one call at a time."""
    import numpy as np
    angle = 0
    try:
        from .orientation import predict
        a, prob = predict(im)
        angle = a if a and prob >= ORIENT_MIN_PROB else 0
    except Exception:  # noqa: BLE001  (no orientation model: read the page as it is)
        angle = 0
    up = (im.rotate(angle, expand=True) if angle else im).convert("RGB")
    W, H = up.size
    with _ENGINE_LOCK:
        r = _engine()(np.asarray(up))
    words = []
    boxes = r.boxes if getattr(r, "boxes", None) is not None else []
    per_line = getattr(r, "word_results", None) or ()
    for li, (lbox, ltxt) in enumerate(zip(boxes, r.txts or ())):
        items = per_line[li] if li < len(per_line) and per_line[li] else ((ltxt, 1.0, lbox),)
        for t, _score, box in items:
            if not str(t).strip():
                continue
            xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
            words.append({"t": str(t), "l": li, "b": [round(max(0.0, min(xs) / W), 5), round(max(0.0, min(ys) / H), 5),
                                                      round(min(1.0, max(xs) / W), 5), round(min(1.0, max(ys) / H), 5)]})
    return {"v": VERSION, "angle": angle, "words": words}


def _render(pdf_path: Path, n: int):
    """Page n (1-based) as the GUI shows it (/api/page renders pdf[n-1] the same way), long side RENDER_SIDE."""
    import pypdfium2 as pdfium

    from .pdf import _PDFIUM_LOCK
    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            if not 1 <= n <= len(pdf):
                return None
            page = pdf[n - 1]
            w, h = page.get_size()
            return page.render(scale=min(3.0, RENDER_SIDE / max(w, h, 1))).to_pil()
        finally:
            pdf.close()


def _cache_file(pdf_path: Path, n: int) -> Path:
    return pdf_path.parent / f".{pdf_path.stem}.p{n}.words.json"


def _compute(pdf_path: Path, n: int) -> dict | None:
    f = _cache_file(pdf_path, n)
    try:
        page = json.loads(f.read_text(encoding="utf-8"))
        if page.get("v") == VERSION:
            return page
    except (OSError, ValueError):
        pass
    im = _render(pdf_path, n)
    if im is None:
        return None
    page = read_image(im)
    try:
        f.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return page


def _job(pdf_path: Path, n: int) -> Future:
    global _POOL
    key = (str(pdf_path.resolve()), n)
    with _STATE_LOCK:
        if key in _CACHE:
            fut: Future = Future()
            fut.set_result(_CACHE[key])
            return fut
        if key in _JOBS:
            return _JOBS[key]
        if _POOL is None:
            _POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan-boxes")

        def run():
            try:
                page = _compute(pdf_path, n)
                with _STATE_LOCK:
                    if page is not None:
                        _CACHE[key] = page
                        while len(_CACHE) > _CACHE_MAX:
                            _CACHE.popitem(last=False)
                return page
            finally:
                with _STATE_LOCK:
                    _JOBS.pop(key, None)
        fut = _JOBS[key] = _POOL.submit(run)
        return fut


def prefetch(pdf_path: Path, pages) -> None:
    """Start reading these pages in the background (e.g. while the pipeline runs); no-op without the dependency."""
    if not available():
        return
    for n in pages:
        _job(Path(pdf_path), int(n))


def page_words(pdf_path: Path, n: int, timeout: float = 120) -> dict | None:
    """Word boxes of page n (1-based): cached, in flight (waits), or read now. None without the dependency or on error."""
    if not available():
        return None
    try:
        return _job(Path(pdf_path), int(n)).result(timeout=timeout)
    except Exception:  # noqa: BLE001  (missing models offline, broken page ...: the quote alone is shown, as before)
        return None


def scan_pages(pdf_path: Path, min_chars: int = 40, max_pages: int | None = None,
               garbage_threshold: float = 0.1) -> list[int]:
    """1-based pages the pipeline will OCR: too little own text, or a garbled text layer (same rule as o2j.pdf.load)."""
    import pypdfium2 as pdfium

    from .pdf import _PDFIUM_LOCK, text_quality
    out = []
    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            for i in range(len(pdf) if max_pages is None else min(len(pdf), max_pages)):
                page = pdf[i]
                tp = page.get_textpage()
                text = tp.get_text_range().strip()
                tp.close()
                page.close()
                if len(text) < min_chars or text_quality(text) < garbage_threshold:
                    out.append(i + 1)
        finally:
            pdf.close()
    return out


def locate(pdf_path: Path, items: list[dict]) -> int:
    """Attach `rects` to located evidence items (all on scanned pages) in place; returns how many got a box."""
    done = 0
    for e in items:
        page = page_words(pdf_path, e["page"])
        if page is None:
            continue
        rects = match(page, e.get("quote"), e.get("context"), e.get("value"))
        if rects:
            e["rects"] = rects
            done += 1
    return done
