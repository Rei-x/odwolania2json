"""Evidence boxes on scanned pages (o2j/scan_boxes.py): quote -> local OCR word boxes, GUI only.

The matching tests use synthetic OCR pages (no recogniser needed); one test runs the real recogniser on a sample scan
and is skipped when the optional dependency or its models are missing.
"""
import importlib.util
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT
from PIL import Image, ImageDraw

import gui
from o2j import scan_boxes as S

SCAN = ROOT / "samples" / "skan-silny-szum-przelew.pdf"      # no text layer
DIGITAL = ROOT / "samples" / "czysty-przelew.pdf"            # text layer
CW, GAP, LH = 0.01, 0.01, 0.02                               # synthetic layout: char width, word gap, line height


def page_of(lines: list[str], angle: int = 0, top: float = 0.1, step: float = 0.05) -> dict:
    """Synthetic OCR result: each line at its own y, words left to right, CW per character."""
    words = []
    for li, line in enumerate(lines):
        x, y = 0.05, top + li * step
        for t in line.split():
            words.append({"t": t, "l": li, "b": [x, y, x + CW * len(t), y + LH]})
            x += CW * len(t) + GAP
    return {"v": S.VERSION, "angle": angle, "words": words}


def word(page: dict, text: str) -> dict:
    return next(w for w in page["words"] if w["t"] == text)


def pct(v: float) -> float:
    return round(v * 100, 3)


def test_fold_polish_diacritics_and_punctuation():
    assert S.fold("Łódź, ul. Różana 6") == "lodzulrozana6"
    assert S.fold("ZAŻÓŁĆ GĘŚLĄ JAŹŃ") == "zazolcgeslajazn"
    assert S.fold("34,00 zł") == "3400zl"


def test_single_line_quote_boxes_only_the_quote():
    page = page_of(["Mocodawca Granitix Usługi S.A.", "ul. Różana 6, 90-149 Łódź"])
    rects = S.match(page, "Granitix Usługi S.A.")
    assert len(rects) == 1
    x, y, w, h = rects[0]
    g = word(page, "Granitix")
    assert x == pytest.approx(pct(g["b"][0])) and y == pytest.approx(pct(g["b"][1]))
    assert x > pct(word(page, "Mocodawca")["b"][2])  # the label before the value is not boxed


def test_quote_spanning_three_lines_gives_one_box_per_line():
    page = page_of(["Tytuł przelewu: opłata skarbowa od",
                    "pełnomocnictwa dla Ryszard Mazurkiewicz",
                    "w postępowaniu przed KIO",
                    "Nr ref. operacji: CEN2606184449569."])
    rects = S.match(page, "opłata skarbowa od pełnomocnictwa dla Ryszard Mazurkiewicz w postępowaniu")
    assert len(rects) == 3
    assert [r[1] for r in rects] == sorted(r[1] for r in rects)          # top to bottom
    assert rects[0][0] == pytest.approx(pct(word(page, "opłata")["b"][0]))  # starts at the quote, not at 'Tytuł'
    assert rects[2][1] == pytest.approx(pct(word(page, "postępowaniu")["b"][1]))
    right = word(page, "postępowaniu")["b"][2]
    assert rects[2][0] + rects[2][2] == pytest.approx(pct(right))       # 'przed KIO' left out


def test_ocr_noise_and_missing_diacritics_still_match():
    # PP-OCR reads 'ł' as 't' and drops accents; the quote comes from the VLM text with proper Polish letters
    page = page_of(["Petnomocnicy adw. Jolanta Jablonczyk, nr wpisu WA 23328",
                    "Granitix Ustugi S.A."])
    rects = S.match(page, "Jolanta Jabłończyk")
    assert len(rects) == 1
    jab = word(page, "Jablonczyk,")
    assert rects[0][0] + rects[0][2] < pct(jab["b"][2])                 # trailing comma not boxed
    assert S.match(page, "Granitix Usługi S.A.")


def test_no_match_or_too_short_gives_no_rects():
    page = page_of(["Bank potwierdza, że w dniu 07.06.2026 wykonano przelew 34,00 zł"])
    assert S.match(page, "Krajowa Izba Odwoławcza w Warszawie") == []
    assert S.match(page, "6") == []                                      # under 3 chars: too ambiguous
    assert S.match(page, "35,00") == []                                  # short quotes must match exactly
    assert S.match(page, "34,00")
    assert S.match({"angle": 0, "words": []}, "34,00") == []
    assert S.match(page, None) == []


def test_context_picks_the_right_occurrence():
    page = page_of(["Mocodawca Granitix Usługi S.A.", "Dane rejestrowe KRS 9992992231",
                    "Data 12 sierpnia 2026", "Za Granitix Usługi S.A.", "Ryszard Nowakowicz Członek Zarządu"])
    ctx = "Data 12 sierpnia 2026 ....... Za Granitix Usługi S.A. Ryszard Nowakowicz Członek Zarządu"
    top, bottom = page["words"][1]["b"][1], page["words"][-6]["b"][1]
    assert S.match(page, "Granitix Usługi S.A.")[0][1] == pytest.approx(pct(top))
    assert S.match(page, "Granitix Usługi S.A.", context=ctx)[0][1] == pytest.approx(pct(bottom))


def test_partial_word_is_trimmed_to_the_quote():
    page = page_of(["na rachunek nr PL.70953449300090369058127127. prowadzony"])
    w = word(page, "PL.70953449300090369058127127.")
    x, _, width, _ = S.match(page, "70953449300090369058127127")[0]
    assert x > pct(w["b"][0]) and x + width < pct(w["b"][2])
    # one digit missed at the edge by a noisy alignment is still taken in
    page = page_of(["z rachunku nr 0088050991363331687549357 prowadzonego"])
    w = word(page, "0088050991363331687549357")
    x, _, width, _ = S.match(page, "088050991363331687549357")[0]
    assert x == pytest.approx(pct(w["b"][0]))


def test_misread_short_quote_is_found_through_its_context():
    # the noisy scan: the VLM read '34,00', the local OCR '34,09' -> no exact match, but the words around agree
    page = page_of(["Wyposazenie sp. j., wykonano przelew krajowy w kwocie 34,09 na rachunek nr",
                    "PL.70953449300090369058127127. prowadzony dla Oryntę Konsulting sp. k."])
    ctx = ("Uldaris Wyposażenie sp. j., wykonano przelew krajowy w kwocie 34,00 na rachunek nr "
           "PL70953449300090369058127127, prowadzony dla Oryntę")
    assert S.match(page, "34,00") == []
    (x, y, w, h), = S.match(page, "34,00", context=ctx)
    amount = word(page, "34,09")["b"]
    assert x == pytest.approx(pct(amount[0])) and x + w == pytest.approx(pct(amount[2]))
    assert S.match(page, "34,00", context="zupełnie inny akapit o czymś innym, 34,00 i tyle w temacie") == []


def test_value_is_tried_when_the_quote_does_not_match():
    page = page_of(["Kwota operacji 200,00 PLN"])
    assert S.match(page, "dwieście złotych", value="200,00 PLN")
    assert S.match(page_of(["ul. Bankowa 340"]), "nie ma", value=34.0) == []  # numbers are not page text


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_unrotate_maps_upright_boxes_back_onto_the_rendered_page(angle):
    W, H, box = 400, 300, (50, 40, 120, 70)
    im = Image.new("L", (W, H), 255)
    ImageDraw.Draw(im).rectangle(box, fill=0)
    up = im.rotate(angle, expand=True)  # what o2j.orientation.correct / scan_boxes.read_image do
    x0, y0, x1, y1 = Image.eval(up, lambda v: 255 - v).getbbox()
    uw, uh = up.size
    got = S._unrotate([x0 / uw, y0 / uh, x1 / uw, y1 / uh], angle)
    want = [box[0] / W, box[1] / H, (box[2] + 1) / W, (box[3] + 1) / H]
    assert got == pytest.approx(want, abs=1.5 / min(W, H))


def test_rotated_page_trims_along_the_text_direction():
    page = page_of(["nr PL.70953449300090369058127127."], angle=90)
    full = S._unrotate(word(page, "PL.70953449300090369058127127.")["b"], 90)
    x, y, w, h = S.match(page, "70953449300090369058127127")[0]
    assert w == pytest.approx(pct(full[2] - full[0]))      # across the line: whole line height
    assert h < pct(full[3] - full[1])                      # along the line (vertical on this page): trimmed


# ---------------------------------------------------------------- GUI wiring and graceful degradation
@pytest.fixture
def no_rapidocr(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None if name == "rapidocr" else real(name, *a, **k))
    monkeypatch.setattr(S, "_AVAILABLE", None)
    yield
    S._AVAILABLE = None


def scan_evidence():
    return [{"field": "kwota", "value": 34.0, "method": "located", "page": 1, "quote": "34,00",
             "context": "wykonano przelew krajowy w kwocie 34,00 na rachunek nr PL70953449300090369058127127"},
            {"field": "x", "value": "y", "method": "inferred"}]


def test_missing_dependency_degrades_to_quote_only(no_rapidocr, tmp_path):
    assert S.available() is False
    pdf = tmp_path / SCAN.name
    shutil.copy(SCAN, pdf)
    assert S.page_words(pdf, 1) is None
    S.prefetch(pdf, [1])
    assert not S._JOBS
    ev = scan_evidence()
    gui.highlight_rects(pdf, ev, ocr_pages=[1])
    assert all("rects" not in e for e in ev)
    assert not list(tmp_path.glob(".*.words.json"))

    class Pipe:
        _ocr = object()
        s = {"ocr": {}}
    gui.prefetch_scan_boxes(pdf, Pipe())  # no-op, no error


def test_highlight_rects_uses_word_boxes_only_on_scanned_pages(monkeypatch, tmp_path):
    calls = []
    page = page_of(["Wyposażenie sp. j., wykonano przelew krajowy w kwocie 34,00 na rachunek nr"])

    def fake(path, n, timeout=120):
        calls.append(n)
        return page
    monkeypatch.setattr(S, "page_words", fake)
    ev = scan_evidence()
    gui.highlight_rects(SCAN, ev, ocr_pages=[1])
    assert calls == [1] and ev[0]["rects"] == S.match(page, "34,00", ev[0]["context"])
    ev = scan_evidence()
    gui.highlight_rects(SCAN, ev)  # ocr_pages unknown: an empty text layer marks the scan
    assert ev[0]["rects"]
    calls.clear()
    ev = [{"field": "kwota", "method": "located", "page": 1, "quote": "200,00 PLN"},
          {"field": "nic", "method": "located", "page": 1, "quote": "tekstu nie ma na stronie"}]
    gui.highlight_rects(DIGITAL, ev, ocr_pages=[])
    assert ev[0]["rects"] and "rects" not in ev[1] and calls == []  # digital page: text layer only, no OCR


def test_scan_pages_follow_the_pipeline_rule():
    assert S.scan_pages(SCAN) == [1]
    assert S.scan_pages(DIGITAL) == []
    assert S.scan_pages(ROOT / "samples" / "skan-obrocony-90-odwolanie.pdf", max_pages=1) == [1]


def test_cli_never_imports_the_gui_ocr():
    code = ("import sys; sys.path.insert(0, %r); import run; "
            "bad = [m for m in ('o2j.scan_boxes', 'rapidocr', 'cv2') if m in sys.modules]; "
            "assert not bad, bad") % str(ROOT)
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT, timeout=60)


def test_real_recogniser_boxes_the_amount_on_a_noisy_scan(tmp_path):
    if not S.available():
        pytest.skip("rapidocr not installed (optional: requirements-gui.txt)")
    pdf = tmp_path / SCAN.name
    shutil.copy(SCAN, pdf)
    page = S.page_words(pdf, 1)
    if page is None:
        pytest.skip("recogniser models not available offline")
    assert page["angle"] == 0 and len(page["words"]) > 50
    assert (tmp_path / f".{pdf.stem}.p1.words.json").exists()   # cached per (document, page)
    (x, y, w, h), = S.match(page, "34,00", scan_evidence()[0]["context"])
    assert 40 < x < 55 and 24 < y < 30 and w < 6                 # 'w kwocie 34,00' on the third text line
    assert S.page_words(pdf, 1) is page                          # second call: memory cache
