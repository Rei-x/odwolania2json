"""Profile `auto`: scanned (OCR'd) documents go straight to the scan model; digital ones keep the cascade.

Offline: OCR engine and LLM are stubs. The scan is samples/skan-silny-szum-przelew.pdf (no text layer);
the stub OCR returns the text of the digital original (data/train/przyklad_26).
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

from conftest import ROOT, TRAIN

from o2j import pdf as P
from o2j import router as R
from o2j import tracing as T

SCAN = ROOT / "samples" / "skan-silny-szum-przelew.pdf"
ORIGINAL = TRAIN / "przyklad_26" / "potwierdzenie_przelewu.pdf"
BIG = "mistralai/ministral-8b-2512"


class _Stub:
    model = "small-model"

    def __init__(self, gold: dict, doctype: str):
        self.gold, self.doctype = gold, doctype
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def extract_json(self, system, user, schema, name="extraction", images=None, model=None, temperature=None):
        m = model or self.model
        with self._lock:
            self.calls.append((name, m))
        T.record_usage(m, {"cost": 0.0, "prompt_tokens": 1, "completion_tokens": 1})
        if name == "classification":
            return {"typ": self.doctype}, {"model": m, "usage": {}, "raw": "{}", "attempts": 1}
        if name == "repair":
            return {"poprawki": []}, {"model": m, "usage": {}, "raw": "{}", "attempts": 1}
        out = copy.deepcopy(self.gold)
        if m == self.model:  # the small model gets the amount wrong -> rules disagree -> escalation
            out["przelew_bankowy"]["kwota"] = 1.0
        return out, {"model": m, "usage": {}, "raw": json.dumps(out), "attempts": 1}


def _pipe():
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline

    s = load_settings(profile="auto")
    s["llm"] = {**s["llm"], "base_url": "http://127.0.0.1:9/v1", "api_key": "none", "model": "small-model",
                "retries": 0}
    s["ocr"] = {**s.get("ocr", {}), "engine": "none", "preprocess": None}
    p = Pipeline(s)
    gold = json.loads((TRAIN / "przyklad_26" / "przelew.json").read_text(encoding="utf-8"))
    p.llm = _Stub(gold, "przelew")
    original = P.load(ORIGINAL).pages
    p._ocr = lambda png, _pages=iter(original): next(_pages).text  # page i of the scan -> page i of the original
    return p


def test_scan_goes_straight_to_scan_model():
    p = _pipe()
    doctype, result, trace = p.process(SCAN, {"przyklad_26"})
    assert doctype == "przelew" and trace["ocr_pages"]
    names = [n for n, _ in p.llm.calls]
    assert "classification" not in names  # rules are confident on this text -> no LLM vote
    assert {m for n, m in p.llm.calls if n != "classification"} == {BIG}  # no small-model pass at all
    assert trace["first_pass_model"] == BIG
    assert not trace["router"]["escalate"] and "dokument wymagał OCR" not in trace["router"]["reasons"]
    by = {s["id"]: s for s in trace["steps"]}
    assert by["extract"]["models"] == [BIG]


def test_digital_document_keeps_small_first_pass_and_cascade():
    p = _pipe()
    p._ocr = None
    doctype, result, trace = p.process(ORIGINAL, {"przyklad_26"})
    assert doctype == "przelew" and not trace["ocr_pages"]
    extract_models = [m for n, m in p.llm.calls if n == "przelew"]
    assert extract_models[0] == "small-model" and BIG in extract_models  # 3B first, 8B on escalation
    assert trace["router"]["escalate"] and trace["first_pass_model"] == "small-model"


def test_remaining_levels():
    cfg = {"escalation": {"levels": [["a"], ["b"], ["c"]]}}
    assert R.remaining_levels(cfg, None) == [["a"], ["b"], ["c"]]
    assert R.remaining_levels(cfg, "b") == [["c"]]
    assert R.remaining_levels(cfg, "c") == []
    assert R.remaining_levels(cfg, "x") == [["a"], ["b"], ["c"]]
    assert R.remaining_levels({"escalation": {"levels": [[BIG]]}}, BIG) == []


def test_ocr_reason_disabled_in_settings():
    from o2j.config import load_settings
    s = load_settings(profile="auto")
    d = R.difficulty({"a": 1}, None, [], True, None, s["router"])
    assert not d["escalate"]


def test_scan_fixture_has_no_text_layer():
    assert Path(SCAN).exists()
    doc = P.load(SCAN)
    assert all(len(pg.text.strip()) < 40 for pg in doc.pages)


def test_hedged_request_returns_first_success():
    import time

    from o2j.llm import hedged
    calls = []

    def slow_then_fast():
        n = len(calls)
        calls.append(n)
        time.sleep(0.5 if n == 0 else 0.01)  # first request stalls, the duplicate answers quickly
        return n
    t = time.time()
    assert hedged(slow_then_fast, 0.05) == 1 and time.time() - t < 0.4 and len(calls) == 2
    calls.clear()
    assert hedged(lambda: calls.append(1) or "ok", 0.5) == "ok" and len(calls) == 1  # fast: no duplicate
    assert hedged(lambda: "plain", None) == "plain"


def test_hedged_raises_only_when_all_fail():
    import pytest

    from o2j.llm import hedged
    with pytest.raises(ValueError):
        hedged(lambda: (_ for _ in ()).throw(ValueError("x")), 0.01)


def test_verify_stops_when_repair_changes_nothing():
    """A repair that hands back the flagged value unchanged ends the loop (no second identical round)."""
    p = _pipe()
    bad = "0088050991363331687549357"  # 25 digits -> pattern issue that the model cannot fix
    stub = p.llm
    orig = stub.extract_json

    def extract_json(system, user, schema, name="extraction", **kw):
        if name == "repair":
            with stub._lock:
                stub.calls.append((name, kw.get("model")))
            return {"poprawki": [{"field": "przelew_bankowy.z_rachunku", "value": "PL" + bad, "uzasadnienie": "x"}]}, {}
        out, meta = orig(system, user, schema, name=name, **kw)
        if name == "przelew":
            out["przelew_bankowy"]["z_rachunku"] = bad
        return out, meta
    stub.extract_json = extract_json
    _, result, trace = p.process(SCAN, {"przyklad_26"})
    assert [n for n, _ in stub.calls].count("repair") == 1
    assert len(trace["verification"]["rounds"]) == 1 and trace["verification"]["remaining_issues"]
