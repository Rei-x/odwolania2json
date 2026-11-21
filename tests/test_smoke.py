"""CLI / pipeline smoke tests with the LLM replaced by an offline stub."""
import json
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT, TRAIN


def test_run_help():
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--help"], capture_output=True, text=True, timeout=60,
                       cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "eval" in r.stdout and "--input" in r.stdout


class _DeadLLM:
    """Stands in for o2j.llm.LLM: every call fails as if the API were unreachable."""
    model = "offline-stub"

    def __init__(self):
        self.calls = 0

    def extract_json(self, *a, **kw):
        self.calls += 1
        raise RuntimeError("LLM unavailable (offline test)")


@pytest.fixture
def pipe():
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline

    s = load_settings()
    s["llm"] = {"base_url": "http://127.0.0.1:9/v1", "api_key": "none", "model": "offline-stub", "retries": 0}
    s["ocr"] = {**s.get("ocr", {}), "engine": "none", "preprocess": None}
    p = Pipeline(s)
    p.llm = _DeadLLM()
    return p


def test_unreadable_file_writes_empty_json(pipe, tmp_path):
    inp, out = tmp_path / "in" / "sprawa", tmp_path / "out"
    inp.mkdir(parents=True)
    (inp / "dokument.pdf").write_bytes(b"\x00garbage, not a pdf")
    summary = pipe.run_dir(tmp_path / "in", out, tmp_path / "trace", workers=1, log=lambda *_: None)
    assert json.loads((out / "sprawa" / "dokument.json").read_text()) == {}
    assert summary[0]["doctype"] == "NIEDOPASOWANY"
    trace = json.loads((tmp_path / "trace" / "sprawa" / "dokument.trace.json").read_text())
    assert trace["load_error"]


def test_llm_failure_falls_back_to_skeleton(pipe, tmp_path):
    inp, out = tmp_path / "in" / "sprawa", tmp_path / "out"
    inp.mkdir(parents=True)
    shutil.copy(TRAIN / "przyklad_01" / "odwolanie.pdf", inp / "dokument.pdf")
    summary = pipe.run_dir(tmp_path / "in", out, None, workers=1, log=lambda *_: None)
    assert pipe.llm.calls >= 1
    assert summary[0]["doctype"] == "odwolanie" and summary[0]["error"]
    assert json.loads((out / "sprawa" / "dokument.json").read_text()) == pipe.specs["odwolanie"].skeleton()
