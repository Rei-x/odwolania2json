"""Structured processing trace: `trace["steps"]` = [{id, label, t_start, duration_s, model?, cost_usd?, tokens?,
calls?, detail}].

Purely observational: nothing here changes what the pipeline computes.
- LLM usage is attributed to the step that is running via a context variable (`meter`); llm.track() reports
  every API response here. Thread pools that make LLM calls on behalf of a step must run their work through
  `bind()` so the worker threads see the same meters.
- Low-level code (pdf loading, preprocessing) can leave `note()`s that the running step collects.
"""
from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager

_METERS: contextvars.ContextVar[tuple] = contextvars.ContextVar("o2j_meters", default=())
_NOTES: contextvars.ContextVar[list | None] = contextvars.ContextVar("o2j_notes", default=None)
_LOCK = threading.Lock()


def _usage_dict(usage) -> dict:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return dict(usage) if isinstance(usage, dict) else {}


def record_usage(model: str | None, usage) -> None:
    """Called for every LLM API response (from llm.track)."""
    meters = _METERS.get()
    if not meters:
        return
    d = _usage_dict(usage)
    with _LOCK:
        for m in meters:
            m["calls"] += 1
            m["cost_usd"] += float(d.get("cost") or 0)
            m["prompt_tokens"] += int(d.get("prompt_tokens") or 0)
            m["completion_tokens"] += int(d.get("completion_tokens") or 0)
            if model and model not in m["models"]:
                m["models"].append(model)


def _new_meter() -> dict:
    return {"calls": 0, "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "models": []}


@contextmanager
def meter():
    m = _new_meter()
    tok = _METERS.set(_METERS.get() + (m,))
    try:
        yield m
    finally:
        _METERS.reset(tok)


def bind(fn):
    """fn that runs in (a copy of) the caller's context, e.g. for ThreadPoolExecutor.map in worker threads."""
    ctx = contextvars.copy_context()

    def run(*a, **kw):
        return ctx.copy().run(fn, *a, **kw)
    return run


def note(kind: str, data: dict) -> None:
    """Leave an observation for the step that is currently running (no-op outside a step)."""
    notes = _NOTES.get()
    if notes is not None:
        with _LOCK:
            notes.append({"kind": kind, **data})


@contextmanager
def collect_notes():
    notes: list = []
    tok = _NOTES.set(notes)
    try:
        yield notes
    finally:
        _NOTES.reset(tok)


class Steps:
    """Recorder of pipeline steps. `with steps.step("load", "Wczytanie") as d: d["pages"] = 3`."""

    def __init__(self, t0: float | None = None):
        self.t0 = t0 if t0 is not None else time.time()
        self.items: list[dict] = []

    @contextmanager
    def step(self, sid: str, label: str, model: str | None = None):
        detail: dict = {}
        item = {"id": sid, "label": label, "t_start": round(time.time() - self.t0, 3), "detail": detail}
        if model:
            item["model"] = model
        t = time.time()
        with meter() as m:
            try:
                yield detail
            except BaseException as e:
                item["error"] = repr(e)[:300]
                raise
            finally:
                item["duration_s"] = round(time.time() - t, 3)
                if m["calls"]:
                    item["calls"] = m["calls"]
                    item["cost_usd"] = round(m["cost_usd"], 6)
                    item["tokens"] = {"prompt": m["prompt_tokens"], "completion": m["completion_tokens"]}
                    item["models"] = m["models"]
                    item.setdefault("model", m["models"][0] if m["models"] else None)
                self.items.append(item)

    def summary(self) -> dict:
        models: list[str] = []
        for s in self.items:
            for mm in s.get("models") or ([s["model"]] if s.get("model") else []):
                if mm and mm not in models:
                    models.append(mm)
        return {"total_s": round(time.time() - self.t0, 3), "steps": len(self.items),
                "llm_calls": sum(s.get("calls", 0) for s in self.items),
                "cost_usd": round(sum(s.get("cost_usd", 0.0) for s in self.items), 6),
                "tokens": {"prompt": sum((s.get("tokens") or {}).get("prompt", 0) for s in self.items),
                           "completion": sum((s.get("tokens") or {}).get("completion", 0) for s in self.items)},
                "models": models}


def preview(text: str | None, n: int = 600) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[:n].rstrip() + " …"
