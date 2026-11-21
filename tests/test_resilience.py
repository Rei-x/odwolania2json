"""Batch robustness: API retries/backoff/Retry-After, global concurrency cap, fail-fast on a bad key,
failure isolation per document, resumable runs (o2j/api.py, Pipeline.run_dir, run.py)."""
import email.utils
import json
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openai
import pytest
from conftest import ROOT, TRAIN

from o2j import api

try:  # openai >= 3 ships its transport as httpx2
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx


def _err(status: int, headers: dict | None = None):
    req = httpx.Request("POST", "http://test/v1/chat/completions")
    resp = httpx.Response(status, headers=headers or {}, request=req)
    cls = {400: openai.BadRequestError, 401: openai.AuthenticationError, 402: openai.APIStatusError,
           403: openai.PermissionDeniedError, 429: openai.RateLimitError, 500: openai.InternalServerError,
           503: openai.InternalServerError}[status]
    return cls(f"status {status}", response=resp, body=None)


@pytest.fixture(autouse=True)
def fast_api():
    saved = api.settings()
    api.configure({"backoff_base": 0.01, "backoff_cap": 0.02, "max_retry_after": 0.05, "retries": 5,
                   "timeout_retries": 1, "max_concurrency": 16})
    api.reset_stats()
    api.QUIET = True
    yield
    api.configure(saved)
    api.QUIET = False
    api.reset_stats()


def _flaky(errors, result="ok"):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return result
    return fn, calls


# ------------------------------------------------------------------ retry policy
def test_retry_after_header_forms():
    assert api.retry_after(_err(429, {"retry-after": "7"})) == 7
    assert api.retry_after(_err(429, {"retry-after-ms": "1500"})) == 1.5
    date = email.utils.formatdate(time.time() + 30, usegmt=True)
    assert 25 <= api.retry_after(_err(429, {"retry-after": date})) <= 31
    assert api.retry_after(_err(429, {"retry-after": "garbage"})) is None
    assert api.retry_after(_err(429)) is None


def test_backoff_uses_retry_after_capped_and_jittered():
    api.configure({"max_retry_after": 120})
    d = api.backoff_delay(0, _err(429, {"retry-after": "3"}))
    assert 3 <= d <= 4
    assert api.backoff_delay(0, _err(429, {"retry-after": "9999"})) <= 121


def test_exponential_backoff_with_jitter_and_cap():
    api.configure({"backoff_base": 1.0, "backoff_cap": 30})
    for attempt, (lo, hi) in enumerate([(0.5, 1), (1, 2), (2, 4), (4, 8), (8, 16), (15, 30), (15, 30)]):
        ds = [api.backoff_delay(attempt) for _ in range(50)]
        assert all(lo <= d <= hi for d in ds), (attempt, min(ds), max(ds))
        assert len({round(d, 6) for d in ds}) > 1  # jitter: threads do not retry in lockstep


def test_429_and_5xx_are_retried_until_success():
    fn, calls = _flaky([_err(429, {"retry-after": "0"}), _err(503), _err(500)])
    assert api.request(fn) == "ok"
    assert len(calls) == 4
    assert api.STATS["retries"] == 3 and api.STATS["rate_limited"] == 1 and api.STATS["server_errors"] == 2


def test_gives_up_after_retry_budget():
    fn, calls = _flaky([_err(429)] * 10)
    with pytest.raises(openai.RateLimitError):
        api.request(fn, retries=3)
    assert len(calls) == 4 and api.STATS["failed"] == 1


def test_timeouts_have_their_own_small_budget():
    to = openai.APITimeoutError(request=httpx.Request("POST", "http://test"))
    fn, calls = _flaky([to, to, to])
    with pytest.raises(openai.APITimeoutError):
        api.request(fn)  # timeout_retries=1 -> 2 attempts
    assert len(calls) == 2
    fn, calls = _flaky([to])
    assert api.request(fn) == "ok"


@pytest.mark.parametrize("status", [401, 402])
def test_bad_key_or_no_credits_fail_fast(status):
    fn, calls = _flaky([_err(status)] * 5)
    t = time.time()
    with pytest.raises(api.FatalAPIError) as ei:
        api.request(fn)
    assert len(calls) == 1 and time.time() - t < 0.5
    assert str(status) in str(ei.value)


@pytest.mark.parametrize("status", [400, 403])
def test_client_errors_are_not_retried(status):
    fn, calls = _flaky([_err(status)] * 5)
    with pytest.raises(openai.APIStatusError):
        api.request(fn)
    assert len(calls) == 1


def test_429_pauses_all_threads():
    """A 429 with Retry-After sets a shared cool-down: other threads do not send during it."""
    api.configure({"max_retry_after": 0.4})
    sent = []
    first = threading.Event()

    def throttled():
        sent.append(time.monotonic())
        if len(sent) == 1:
            first.set()
            raise _err(429, {"retry-after": "0.3"})
        return "ok"
    t0 = time.monotonic()
    th = threading.Thread(target=lambda: api.request(throttled))
    th.start()
    first.wait(2)
    time.sleep(0.02)
    assert api.request(lambda: sent.append(time.monotonic()) or "ok") == "ok"  # another worker
    th.join(3)
    assert all(t - t0 >= 0.29 for t in sent[1:]), [round(t - t0, 3) for t in sent]


def test_global_concurrency_cap_shared_by_threads():
    api.configure({"max_concurrency": 3})
    lock, live, peak = threading.Lock(), [0], [0]

    def fn():
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.03)
        with lock:
            live[0] -= 1
        return 1
    ths = [threading.Thread(target=lambda: api.request(fn)) for _ in range(20)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(5)
    assert peak[0] == 3


def test_llm_client_retries_through_api(monkeypatch):
    from o2j.llm import LLM
    llm = LLM({"base_url": "http://127.0.0.1:9/v1", "api_key": "x", "model": "m", "hedge_after": None})
    resp = type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": '{"a": 1}'})(),
                                                     "finish_reason": "stop"})()],
                          "usage": None, "model": "m"})()
    fn, calls = _flaky([_err(429, {"retry-after": "0"}), _err(503)], resp)
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kw: fn())
    out, meta = llm.extract_json("s", "u", None)
    assert out == {"a": 1} and len(calls) == 3
    fn, calls = _flaky([_err(401)], resp)
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kw: fn())
    with pytest.raises(api.FatalAPIError):
        llm.extract_json("s", "u", None)
    assert len(calls) == 1


# ------------------------------------------------------------------ batch: isolation, fatal stop, resume
class _StubLLM:
    model = "stub"


@pytest.fixture
def pipe():
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline
    s = load_settings()
    s["llm"] = {"base_url": "http://127.0.0.1:9/v1", "api_key": "none", "model": "stub", "retries": 0}
    s["ocr"] = {**s.get("ocr", {}), "engine": "none", "preprocess": None}
    s["paths"]["learned"] = None
    p = Pipeline(s)
    p.llm = _StubLLM()
    return p


def _input(tmp_path, n_cases=3):
    inp = tmp_path / "in"
    for i in range(1, n_cases + 1):
        case = inp / f"sprawa_{i}"
        case.mkdir(parents=True)
        for name in ("odwolanie.pdf", "pelnomocnictwo.pdf"):
            shutil.copy(TRAIN / f"przyklad_0{i}" / name, case / name)
    return inp


def _fake_process(calls, fail=(), fatal=()):
    def process(path, exclude=frozenset()):
        key = f"{path.parent.name}/{path.name}"
        calls.append(key)
        if key in fatal:
            raise api.FatalAPIError("nieprawidłowy klucz API (HTTP 401)")
        if key in fail:
            raise RuntimeError("provider exploded")
        doctype = path.stem
        return doctype, {"ok": key}, {"file": str(path), "doctype": doctype, "elapsed_s": 0.0}
    return process


def test_one_failing_document_does_not_stop_the_batch(pipe, tmp_path):
    inp, out = _input(tmp_path), tmp_path / "out"
    calls = []
    pipe.process = _fake_process(calls, fail={"sprawa_2/odwolanie.pdf"})
    summary = pipe.run_dir(inp, out, tmp_path / "trace", workers=3, log=lambda *_: None)
    assert len(summary) == 6 and len(calls) == 6
    bad = next(x for x in summary if x["file"] == "sprawa_2/odwolanie.json")
    assert "provider exploded" in bad["error"]
    assert json.loads((out / "sprawa_2" / "odwolanie.json").read_text())  # best-effort skeleton, valid JSON
    assert json.loads((out / "sprawa_1" / "odwolanie.json").read_text()) == {"ok": "sprawa_1/odwolanie.pdf"}
    tr = json.loads((tmp_path / "trace" / "sprawa_2" / "odwolanie.trace.json").read_text())
    assert "provider exploded" in tr["error"]


def test_resume_skips_finished_and_retries_failed(pipe, tmp_path):
    inp, out, trace = _input(tmp_path), tmp_path / "out", tmp_path / "trace"
    calls = []
    pipe.process = _fake_process(calls, fail={"sprawa_2/odwolanie.pdf"})
    pipe.run_dir(inp, out, trace, workers=2, log=lambda *_: None)
    (out / "sprawa_3" / "pelnomocnictwo.json").write_text('{"half-writ')  # corrupted output -> redo
    (out / "sprawa_1" / "pelnomocnictwo.json").unlink()                    # missing output -> redo
    calls.clear()
    pipe.process = _fake_process(calls)
    summary = pipe.run_dir(inp, out, trace, workers=2, log=lambda *_: None, resume=True)
    assert sorted(calls) == ["sprawa_1/pelnomocnictwo.pdf", "sprawa_2/odwolanie.pdf", "sprawa_3/pelnomocnictwo.pdf"]
    assert len(summary) == 6 and sum(x["resumed"] for x in summary) == 3
    assert not any(x["error"] for x in summary)
    assert json.loads((out / "sprawa_2" / "odwolanie.json").read_text()) == {"ok": "sprawa_2/odwolanie.pdf"}
    calls.clear()
    pipe.run_dir(inp, out, trace, workers=2, log=lambda *_: None, resume=True)
    assert calls == []  # everything done
    pipe.run_dir(inp, out, trace, workers=2, log=lambda *_: None, resume=False)  # --force
    assert len(calls) == 6


def test_fatal_error_stops_batch_and_keeps_finished(pipe, tmp_path):
    inp, out, trace = _input(tmp_path), tmp_path / "out", tmp_path / "trace"
    calls = []
    pipe.process = _fake_process(calls, fatal={"sprawa_1/pelnomocnictwo.pdf"})
    with pytest.raises(api.FatalAPIError):
        pipe.run_dir(inp, out, trace, workers=1, log=lambda *_: None)
    assert calls == ["sprawa_1/odwolanie.pdf", "sprawa_1/pelnomocnictwo.pdf"]  # nothing scheduled after the fatal error
    assert (out / "sprawa_1" / "odwolanie.json").exists()
    assert not (out / "sprawa_1" / "pelnomocnictwo.json").exists()           # no fake output: a rerun will do it
    calls.clear()
    pipe.process = _fake_process(calls)
    pipe.run_dir(inp, out, trace, workers=2, log=lambda *_: None, resume=True)
    assert sorted(calls) == sorted(["sprawa_1/pelnomocnictwo.pdf"] + [f"sprawa_{i}/{n}" for i in (2, 3)
                                                               for n in ("odwolanie.pdf", "pelnomocnictwo.pdf")])


def test_fatal_error_does_not_wait_for_documents_in_flight(pipe, tmp_path):
    inp, out = _input(tmp_path), tmp_path / "out"
    release = threading.Event()
    base = _fake_process([], fatal={"sprawa_1/odwolanie.pdf"})

    def process(path, exclude=frozenset()):
        if path.parent.name != "sprawa_1" or path.name != "odwolanie.pdf":
            release.wait(10)  # a slow request (e.g. a big scan upload) still in flight
        else:
            time.sleep(0.05)
        return base(path, exclude)
    pipe.process = process
    t = time.time()
    with pytest.raises(api.FatalAPIError):
        pipe.run_dir(inp, out, None, workers=4, log=lambda *_: None)
    assert time.time() - t < 2
    release.set()


def test_interrupted_run_keeps_finished_documents(pipe, tmp_path):
    """Ctrl+C in the middle: documents finished so far are on disk (written one by one), no temp files."""
    inp, out = _input(tmp_path, 2), tmp_path / "out"
    base = _fake_process([])
    n = []

    def process(path, exclude=frozenset()):
        n.append(1)
        if len(n) == 4:
            raise KeyboardInterrupt
        return base(path, exclude)
    pipe.process = process
    with pytest.raises(KeyboardInterrupt):
        pipe.run_dir(inp, out, None, workers=1, log=lambda *_: None)
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*.json")) == [
        "sprawa_1/odwolanie.json", "sprawa_1/pelnomocnictwo.json", "sprawa_2/odwolanie.json"]
    assert not list(out.rglob(".*.tmp"))


# ------------------------------------------------------------------ CLI end to end against a fake provider
class _Provider(BaseHTTPRequestHandler):
    status = 401
    hits = 0

    def do_POST(self):  # noqa: N802
        type(self).hits += 1
        self.rfile.read(int(self.headers.get("content-length") or 0))
        body = json.dumps({"error": {"message": "No auth credentials found", "code": self.status}}).encode()
        self.send_response(self.status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_cli_invalid_key_fails_fast_with_clear_message(tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        inp = _input(tmp_path, 3)
        env = {"PATH": "/usr/bin:/bin", "O2J_LLM_BASE_URL": f"http://127.0.0.1:{srv.server_port}/v1",
               "O2J_LLM_API_KEY": "sk-invalid", "O2J_LLM_MODEL": "m", "HOME": str(tmp_path)}
        t = time.time()
        r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--input", str(inp), "--output", str(tmp_path / "out"),
                            "--trace", str(tmp_path / "trace"), "--profile", "standard", "--workers", "2"],
                           capture_output=True, text=True, timeout=120, env=env, cwd=tmp_path)
        assert r.returncode == 2, r.stdout + r.stderr
        assert time.time() - t < 60
        assert "401" in r.stderr and "O2J_LLM_API_KEY" in r.stderr
        assert _Provider.hits <= 4  # no retry storm: each in-flight document hit it once at most
    finally:
        srv.shutdown()
