import io

import pytest
from conftest import TRAIN
from PIL import Image

from o2j import pdf as P

SAMPLE = TRAIN / "przyklad_01" / "odwolanie.pdf"


def test_load_training_pdf():
    doc = P.load(SAMPLE)
    assert doc.pages
    assert all(p.text.strip() for p in doc.pages)
    assert [p.number for p in doc.pages] == list(range(1, len(doc.pages) + 1))
    assert all(p.source == "text" and p.image is None for p in doc.pages)
    assert not doc.ocr_used
    assert "ODWOŁANIE" in doc.text().upper()


def test_max_pages_and_text_format():
    full = P.load(SAMPLE)
    one = P.load(SAMPLE, max_pages=1)
    assert len(one.pages) == 1
    assert one.text().startswith("=== Strona 1 ===\n")
    assert full.text(1) == one.text()


@pytest.mark.parametrize("name", ["pelnomocnictwo.pdf", "przelew.pdf"])
def test_other_doctypes_have_text(name):
    doc = P.load(TRAIN / "przyklad_02" / name)
    assert doc.pages and all(p.text.strip() for p in doc.pages)


def test_ocr_not_called_for_text_pages():
    calls = []
    P.load(SAMPLE, ocr=lambda png: calls.append(png) or "x")
    assert calls == []


def test_ocr_called_for_pages_below_min_chars():
    doc = P.load(SAMPLE, ocr=lambda png: "OCR TEXT", min_chars=10**9, max_pages=2, dpi=30)
    assert [p.source for p in doc.pages] == ["ocr", "ocr"]
    assert all(p.text == "OCR TEXT" and p.image.startswith(b"\x89PNG") for p in doc.pages)


def _png(tmp_path, name="scan.png"):
    path = tmp_path / name
    Image.new("RGB", (60, 40), "white").save(path)
    return path


def test_image_input_with_ocr(tmp_path):
    seen = []
    doc = P.load(_png(tmp_path), ocr=lambda png: seen.append(png) or "  Skan tekstu  ")
    assert len(doc.pages) == 1
    p = doc.pages[0]
    assert p.source == "ocr" and p.text == "Skan tekstu"
    assert Image.open(io.BytesIO(p.image)).size == (60, 40)
    assert seen == [p.image]


def test_image_input_without_ocr(tmp_path):
    doc = P.load(_png(tmp_path))
    assert len(doc.pages) == 1 and doc.pages[0].text == "" and doc.pages[0].image


def test_corrupted_pdf_raises(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(Exception):
        P.load(bad)


def test_render_page_png_and_data_url(tmp_path):
    png = P.render_page_png(SAMPLE, 0, dpi=20)
    assert png.startswith(b"\x89PNG")
    assert P.png_data_url(png).startswith("data:image/png;base64,")
    assert P.render_page_png(_png(tmp_path), 0) is None
