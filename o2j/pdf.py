"""PDF -> per-page text. Text layer first; pages without it go to OCR."""
from __future__ import annotations

import base64
import re
import io
from dataclasses import dataclass, field
from pathlib import Path

import threading

import pypdfium2 as pdfium

_PDFIUM_LOCK = threading.Lock()  # pdfium is not thread-safe


def flat_page(pdf, i: int):
    """Page i with annotations/form widgets flattened into content, so text such as electronic-signature
    stamps ("Dokument podpisany przez ...") becomes part of the text layer. Call under _PDFIUM_LOCK."""
    import pypdfium2.raw as pdfium_c
    page = pdf[i]
    try:
        if pdfium_c.FPDFPage_Flatten(page.raw, pdfium_c.FLAT_NORMALDISPLAY) == pdfium_c.FLATTEN_SUCCESS:
            page.close()
            page = pdf[i]
    except Exception:  # noqa: BLE001
        pass
    return page


_POL_WORDS = set("i w z na do oraz nr dnia ul sp się nie od że jest przez dla po zł pln data kwota".split())
_MOJIBAKE = "³œ¹ê¿Ÿæñ¥Œ£¯Æ"


def fix_mojibake(text: str) -> str:
    """Text decoded as cp1252 although it was cp1250 ('P³atnoœci' -> 'Płatności')."""
    if sum(text.count(c) for c in _MOJIBAKE) < 3:
        return text
    try:
        fixed = text.encode("cp1252", errors="strict").decode("cp1250", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        fixed = "".join(c.encode("cp1252").decode("cp1250") if c in _MOJIBAKE else c for c in text)
    pol = lambda t: sum(t.count(c) for c in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")  # noqa: E731
    return fixed if pol(fixed) > pol(text) else text


def text_quality(text: str) -> float:
    """Share of tokens that look like natural-language words. Real pages: ~0.15-0.9 (tables low);
    broken font encodings ('35=(/(:=5$&+81' for 'PRZELEW Z RACHUNKU'): ~0.0."""
    toks = re.findall(r"\S+", text)
    if len(toks) < 15:
        return 1.0
    good = sum(1 for w in toks
               if re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż][a-ząćęłńóśźż]+[.,:;)]?", w)
               or w.lower().strip(".,:;") in _POL_WORDS)
    return good / len(toks)


@dataclass
class Page:
    number: int  # 1-based
    text: str
    source: str  # "text" | "ocr"
    image: bytes | None = None  # rendered page (kept for scanned pages)


@dataclass
class Document:
    path: Path
    pages: list[Page] = field(default_factory=list)

    def text(self, max_pages: int | None = None) -> str:
        pages = self.pages[:max_pages] if max_pages else self.pages
        return "\n\n".join(f"=== Strona {p.number} ===\n{p.text}" for p in pages)

    @property
    def ocr_used(self) -> bool:
        return any(p.source == "ocr" for p in self.pages)


def render_png(page: pdfium.PdfPage, dpi: int = 200) -> bytes:
    img = page.render(scale=dpi / 72).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_EXT = {".pdf"} | IMAGE_EXT


def _load_image(path: Path, ocr, ocr_max_pages: int, prep=None) -> Document:
    from PIL import Image, ImageSequence
    doc = Document(path=path)
    im = Image.open(path)
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG")
        png = buf.getvalue()
        if prep:
            from .preprocess import png_steps
            png = png_steps(prep, png)
        text = ocr(png) if (ocr is not None and i < ocr_max_pages) else ""
        doc.pages.append(Page(i + 1, (text or "").strip(), "ocr", png))
    return doc


def load(path: Path, ocr=None, min_chars: int = 40, dpi: int = 200, max_pages: int | None = None,
         ocr_max_pages: int = 4, prep: list[str] | None = None, garbage_threshold: float = 0.1) -> Document:
    """ocr: callable(png_bytes) -> str, used for pages without a usable text layer."""
    if path.suffix.lower() in IMAGE_EXT:
        return _load_image(path, ocr, ocr_max_pages, prep)
    raw: list[tuple[str, bytes | None]] = []
    with _PDFIUM_LOCK:
        try:
            pdf = pdfium.PdfDocument(str(path))
        except pdfium.PdfiumError:
            pdf = pdfium.PdfDocument(str(path), password="")  # encrypted with empty user password
        n = len(pdf) if max_pages is None else min(len(pdf), max_pages)
        for i in range(n):
            page = flat_page(pdf, i)
            tp = page.get_textpage()
            text = fix_mojibake(tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n"))
            tp.close()
            garbled = len(text.strip()) >= min_chars and text_quality(text) < garbage_threshold
            need = (len(text.strip()) < min_chars or garbled) and ocr is not None and i < ocr_max_pages
            png = render_png(page, dpi) if need else None
            raw.append((text, png))
            page.close()
        pdf.close()
    if prep:  # e.g. auto-orientation / deskew of scanned pages before OCR
        from .preprocess import png_steps
        raw = [(t, png_steps(prep, png) if png is not None else None) for t, png in raw]
    doc = Document(path=path)
    todo = [i for i, (_, png) in enumerate(raw) if png is not None]
    ocr_text = {}
    if todo:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(todo)) as ex:
            ocr_text = dict(zip(todo, ex.map(lambda i: ocr(raw[i][1]), todo)))
    for i, (text, _) in enumerate(raw):
        source = "ocr" if i in ocr_text else "text"
        doc.pages.append(Page(i + 1, (ocr_text.get(i, text) or "").strip(), source, raw[i][1]))
    return doc


def render_page_png(path: Path, i: int, dpi: int = 150) -> bytes | None:
    if path.suffix.lower() != ".pdf":
        return None
    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(str(path))
        try:
            return render_png(flat_page(pdf, i), dpi)
        finally:
            pdf.close()


def png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()
