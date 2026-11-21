"""trace["steps"]: structured, observational processing trace (offline; LLM replaced by a stub)."""
from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import TRAIN
from o2j import tracing as T

STEP_KEYS = {"id", "label", "t_start", "duration_s", "detail"}


class _StubLLM:
    """Answers like a model: classification -> type, extraction -> gold JSON with a formatted NIP; reports usage."""

    model = "stub-model"

    def __init__(self, gold: dict, doctype: str):
        self.gold, self.doctype, self.calls = gold, doctype, 0
        self._lock = threading.Lock()

    def extract_json(self, system, user, schema, name="extraction", images=None, model=None, temperature=None):
        with self._lock:
            self.calls += 1
        m = model or self.model
        T.record_usage(m, {"cost": 0.001, "prompt_tokens": 100, "completion_tokens": 20})
        if name == "classification":
            return {"typ": self.doctype}, {"model": m, "usage": {}, "raw": "{}", "attempts": 1}
        if name == "repair":
            raise RuntimeError("no repair in tests")
        out = copy.deepcopy(self.gold)
        out["Odwolujacy"][0]["nip"] = "999-928-40-65"  # model copies the NIP with dashes -> normalisation
        return out, {"model": m, "usage": {"prompt_tokens": 100}, "raw": json.dumps(out), "attempts": 1}


def _llm_pipe(voting=None):
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline

    s = load_settings()
    s["llm"] = {"base_url": "http://127.0.0.1:9/v1", "api_key": "none", "model": "stub-model", "retries": 0}
    s["ocr"] = {**s.get("ocr", {}), "engine": "none", "preprocess": None}
    s.setdefault("extraction", {})["mode"] = "llm"
    s["router"] = {"enabled": False}
    s["classification"] = {**s.get("classification", {}), "skip_llm_margin": None}  # always exercise the LLM vote
    if voting:
        s["voting"] = voting
    p = Pipeline(s)
    gold = json.loads((TRAIN / "przyklad_01" / "odwolanie.json").read_text(encoding="utf-8"))
    p.llm = _StubLLM(gold, "odwolanie")
    return p


def _check_shape(trace):
    assert isinstance(trace["steps"], list) and trace["steps"]
    for s in trace["steps"]:
        assert STEP_KEYS <= set(s), s.keys()
        assert isinstance(s["detail"], dict) and s["duration_s"] >= 0 and s["t_start"] >= 0
    json.dumps(trace["steps"], ensure_ascii=False)  # serialisable for /api/trace
    summ = trace["steps_summary"]
    assert {"total_s", "llm_calls", "cost_usd", "tokens", "models", "steps"} <= set(summ)


def test_deterministic_steps():
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline

    p = Pipeline(load_settings(profile="deterministyczny"))
    doctype, result, trace = p.process(TRAIN / "przyklad_01" / "odwolanie.pdf")
    _check_shape(trace)
    assert [s["id"] for s in trace["steps"]] == ["load", "classify", "extract", "normalize", "ground"]
    load = trace["steps"][0]["detail"]
    assert load["n_pages"] == trace["pages"] and load["pages"][0]["source"] == "text"
    assert load["pages"][0]["text_layer_chars"] > 0 and "preview" in load["pages"][0]
    cls = trace["steps"][1]["detail"]
    assert cls["decision"] == doctype == "odwolanie" and cls["matched_keywords"]["odwolanie"]
    norm = trace["steps"][3]["detail"]["normalized"]
    assert any(c["field"] == "OdwolanieKIO.czynnosc_dzien" and c["after"] == "2026-03-20" for c in norm)
    ground = trace["steps"][4]["detail"]
    assert ground["counts"] and len(ground["fields"]) == len(trace["evidence"])
    assert trace["steps_summary"]["llm_calls"] == 0 and trace["steps_summary"]["models"] == ["deterministic"]


def test_llm_steps_and_cost_attribution():
    p = _llm_pipe()
    doctype, result, trace = p.process(TRAIN / "przyklad_01" / "odwolanie.pdf")
    _check_shape(trace)
    ids = [s["id"] for s in trace["steps"]]
    assert ids[:6] == ["load", "classify", "few_shot", "extract", "normalize", "ground"] and "verify" in ids
    by = {s["id"]: s for s in trace["steps"]}
    assert by["classify"]["calls"] >= 1 and by["classify"]["detail"]["llm_votes"]
    ex = by["extract"]
    assert ex["calls"] >= 1 and ex["model"] == "stub-model" and ex["cost_usd"] > 0
    assert ex["tokens"]["prompt"] >= 100 and ex["detail"]["raw_output"]["Odwolujacy"][0]["nip"] == "999-928-40-65"
    assert ex["detail"]["prompt_chars"]["user"] > 0
    norm = by["normalize"]["detail"]["normalized"]
    assert any(c["field"] == "Odwolujacy[0].nip" and c["after"] == "9999284065" for c in norm)
    assert result["Odwolujacy"][0]["nip"] == "9999284065"  # behaviour unchanged by tracing
    summ = trace["steps_summary"]
    assert summ["llm_calls"] == p.llm.calls and summ["cost_usd"] == pytest.approx(0.001 * p.llm.calls)
    for k in ("classification", "evidence", "verification", "raw_llm_output", "page_texts", "elapsed_s"):
        assert k in trace  # existing keys are kept


def test_voting_threads_attribute_usage_to_extract_step():
    p = _llm_pipe(voting={"n": 2, "models": ["stub-a", "stub-b"]})
    _, _, trace = p.process(TRAIN / "przyklad_01" / "odwolanie.pdf")
    ex = next(s for s in trace["steps"] if s["id"] == "extract")
    assert ex["calls"] >= 2 and set(ex["models"]) >= {"stub-a", "stub-b"}
    assert len(ex["detail"]["raw_outputs"]) == 2 and ex["detail"]["voting"]["models"] == ["stub-a", "stub-b"]


def test_out_of_scope_stops_after_classification():
    p = _llm_pipe()
    p.llm.doctype = "inny"
    doctype, result, trace = p.process(TRAIN / "przyklad_01" / "odwolanie.pdf")
    assert doctype == "inny" and result == {}
    assert [s["id"] for s in trace["steps"]] == ["load", "classify"]
    assert trace["steps"][1]["detail"]["out_of_scope"] is True


def test_steps_recorder_meter_bind_and_errors():
    st = T.Steps()
    with st.step("a", "A") as d:
        d["x"] = 1

        def work(i):
            T.record_usage(f"m{i}", {"cost": 0.5, "prompt_tokens": 2, "completion_tokens": 1})
            T.note("n", {"i": i})
            return i
        with T.collect_notes() as notes, ThreadPoolExecutor(2) as ex:
            assert list(ex.map(T.bind(work), range(2))) == [0, 1]
        d["notes"] = len(notes)
    with pytest.raises(ValueError):
        with st.step("b", "B"):
            raise ValueError("boom")
    a, b = st.items
    assert a["calls"] == 2 and a["cost_usd"] == 1.0 and a["tokens"] == {"prompt": 4, "completion": 2}
    assert sorted(a["models"]) == ["m0", "m1"] and a["detail"] == {"x": 1, "notes": 2}
    assert "boom" in b["error"] and "calls" not in b
    T.record_usage("outside", {"cost": 1})  # no active step -> ignored
    assert st.summary()["llm_calls"] == 2


def test_failure_keeps_partial_steps():
    p = _llm_pipe()

    def boom(*a, **kw):
        raise RuntimeError("LLM API odrzuciło żądanie (402)")
    p.llm.extract_json = boom
    with pytest.raises(RuntimeError) as ei:
        p.process(TRAIN / "przyklad_01" / "odwolanie.pdf")
    steps = ei.value.trace_steps
    assert [s["id"] for s in steps][:1] == ["load"]
    assert steps[-1]["id"] in ("classify", "extract") and "402" in steps[-1]["error"]
    assert ei.value.trace_steps_summary["steps"] == len(steps)
