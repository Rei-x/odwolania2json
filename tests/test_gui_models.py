"""GUI model swapping: /api/models catalogue, /api/bench_sweep and the per-request model override (offline, stub LLM)."""
import asyncio
import io
import json
import shutil

import pytest
from conftest import ROOT, TRAIN

import gui

PICK = "mistralai/ministral-3b-2512"


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    path = tmp_path / "bench_sweep.json"
    path.write_text(json.dumps({"runs": [
        {"model": PICK, "name": "Mistral: Ministral 3B", "params_b": 3, "points": 20, "eu_providers": ["mistral"],
         "providers": ["mistral"], "train": {"f1": 0.97, "cost": 0.03, "seconds": 60, "per_doc": {}, "error": None},
         "blind": {"f1": 0.96, "cost": 0.04, "seconds": 40, "negatives_ok": "3/3", "per_doc": {"odwolanie": "0.95"}, "error": None}},
        {"model": "acme/gui-agent-7b", "name": "Acme: GUI Agent 7B", "params_b": 7, "points": 20, "eu_providers": [],
         "providers": ["acme"], "train": {"f1": None, "cost": None, "seconds": 5, "per_doc": None, "error": "timeout"},
         "blind": None},
        {"model": "acme/eu-tiny-1b", "name": None, "params_b": 1, "points": 20, "eu_providers": ["nebius"],
         "providers": ["nebius", "acme"], "train": {"f1": 0.9, "cost": 0.001, "seconds": 5}, "blind": {"f1": 0.88}},
    ]}), encoding="utf-8")
    monkeypatch.setenv("O2J_BENCH_SWEEP", str(path))
    gui._pipes.clear()
    yield path
    gui._pipes.clear()


def test_models_catalog_merges_sources(sweep):
    ms = {m["id"]: m for m in gui.models()["models"]}
    assert "deterministic" not in ms
    m = ms[PICK]
    assert m["eu"] and m["params_b"] == 3 and m["points"] == 20 and m["f1_blind"] == 0.96 and m["cost"] == 0.03
    agent = ms["acme/gui-agent-7b"]
    assert agent["eu"] is False and agent["points"] == 20 and agent["f1_blind"] is None and agent["name"] == "GUI Agent 7B"
    assert ms["acme/eu-tiny-1b"]["eu"] is True
    big = ms["deepseek/deepseek-v4.1-flash"]  # from settings.model_params + providers + benchmarks.json
    assert big["points"] == 0 and big["eu"] is True
    assert list(ms).index(PICK) < list(ms).index("acme/gui-agent-7b")  # EU models listed first


def test_bench_sweep_endpoint(sweep, monkeypatch):
    d = gui.bench_sweep()
    assert [r["model"] for r in d["runs"]][:2] == [PICK, "acme/gui-agent-7b"] and d["mtime"]
    monkeypatch.setenv("O2J_BENCH_SWEEP", str(sweep.parent / "missing.json"))
    assert gui.bench_sweep()["runs"] == []
    sweep.write_text('{"runs": [', encoding="utf-8")  # half-written file while the sweep appends
    monkeypatch.setenv("O2J_BENCH_SWEEP", str(sweep))
    assert gui.bench_sweep()["runs"] == []


def test_settings_override_all_three_models(sweep):
    s = gui.settings_for("auto", PICK)
    assert s["llm"]["model"] == s["classification"]["model"] == s["ocr"]["model"] == PICK
    assert s["classification"]["vote_models"] == [] and not s["router"]["enabled"]
    assert s["model_override"] == PICK and s["active_profile"] == "auto"
    s = gui.settings_for("maksymalny", PICK)
    assert s["voting"]["models"] == [PICK]
    # model outside settings.providers: pinned to the EU providers found in the sweep
    s = gui.settings_for("standard", "acme/eu-tiny-1b")
    assert s["providers"]["acme/eu-tiny-1b"]["only"] == ["nebius"]
    # deterministic profile has no LLM -> override ignored
    assert "model_override" not in gui.settings_for("deterministyczny", PICK)
    base = gui.settings_for("auto")
    assert base["llm"]["model"] != PICK or base["classification"]["model"] != PICK  # profile untouched without override


class _StubLLM:
    """Replaces o2j.llm.LLM: records which model each call would use, returns empty JSON (no network)."""
    instances: list = []

    def __init__(self, cfg):
        self.model = cfg["model"]
        self.calls = []
        _StubLLM.instances.append(self)

    def extract_json(self, system, user, schema, name="", images=None, model=None, **kw):
        used = model or self.model
        self.calls.append((name, used))
        if name == "classification":
            return {"typ": "pelnomocnictwo"}, {"model": used, "usage": {}}
        return {}, {"model": used, "usage": {}}


def test_process_uses_chosen_model(sweep, tmp_path, monkeypatch):
    import o2j.pipeline as P
    monkeypatch.setattr(P, "LLM", _StubLLM)
    monkeypatch.setattr(gui, "DATA", tmp_path / "gui_data")
    _StubLLM.instances.clear()
    pdf = next(TRAIN.glob("*/pelnomocnictwo*.pdf"), None) or next(TRAIN.glob("*/*.pdf"))

    class _Upload:  # minimal UploadFile
        filename = pdf.name

        def __init__(self):
            self._b = io.BytesIO(pdf.read_bytes())

        async def read(self):
            return self._b.read()

    out = asyncio.run(gui.process(files=[_Upload()], case="t1", profile="auto", model=PICK))
    doc = out["documents"][0]
    assert doc["trace"]["model_override"] == PICK
    assert doc["trace"]["active_profile"] == "auto"
    llm = _StubLLM.instances[-1]
    assert llm.model == PICK and llm.calls and {m for _, m in llm.calls} == {PICK}
    assert ("auto", PICK) in gui._pipes and gui._pipes[("auto", PICK)].s["ocr"]["model"] == PICK
    # unknown models are rejected before any processing
    with pytest.raises(gui.HTTPException):
        asyncio.run(gui.process(files=[_Upload()], case="t2", profile="auto", model="evil/unknown"))
    shutil.rmtree(tmp_path / "gui_data", ignore_errors=True)


def test_static_pages_wire_the_new_endpoints():
    idx = (ROOT / "o2j" / "static" / "index.html").read_text(encoding="utf-8")
    assert "/api/models" in idx and "fd.append('model'" in idx and "Automatyczny (wg profilu)" in idx
    bench = (ROOT / "o2j" / "static" / "benchmarks.html").read_text(encoding="utf-8")
    assert "/api/bench_sweep" in bench and 'id="sweep"' in bench
