"""Thin client for any OpenAI-compatible chat API (open-weight models hosted by a provider)."""
from __future__ import annotations

import json
import re

from openai import OpenAI

from . import api
from .api import FatalAPIError  # noqa: F401  (re-export)
from .pdf import png_data_url


import threading

_COST_LOCK = threading.Lock()
COST = {"usd": 0.0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "hedged": 0}


def track(resp):
    u = getattr(resp, "usage", None)
    from .tracing import record_usage
    record_usage(getattr(resp, "model", None), u)  # per-step attribution for trace["steps"] (observational)
    if not u:
        return
    d = u.model_dump() if hasattr(u, "model_dump") else dict(u)
    with _COST_LOCK:
        COST["calls"] += 1
        COST["usd"] += float(d.get("cost") or 0)
        COST["prompt_tokens"] += int(d.get("prompt_tokens") or 0)
        COST["completion_tokens"] += int(d.get("completion_tokens") or 0)


_HEDGE_SLOTS = threading.BoundedSemaphore(3)  # duplicates in flight at once (batch runs: no load amplification)


def hedged(fn, after: float | None):
    """fn() with a hedge against provider tail latency: if there is no answer after `after` seconds, one
    duplicate request is started and whichever succeeds first wins (the other is left to finish in the
    background). At most a few duplicates run at a time: when the provider is slow for everyone (large
    batch), extra requests would only add load. after = None/0 -> plain call. Errors surface only when
    every started request failed."""
    if not after or float(after) <= 0:
        return fn()
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from .tracing import bind
    ex = ThreadPoolExecutor(max_workers=2, thread_name_prefix="o2j-hedge")
    try:
        pending = {ex.submit(bind(fn))}
        done, _ = wait(pending, timeout=float(after))
        if not done and _HEDGE_SLOTS.acquire(blocking=False):
            with _COST_LOCK:
                COST["hedged"] += 1

            def dup():
                try:
                    return fn()
                finally:
                    _HEDGE_SLOTS.release()
            pending.add(ex.submit(bind(dup)))
        err = None
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for f in done:
                if f.exception() is None:
                    return f.result()
                err = f.exception()
        raise err
    finally:
        ex.shutdown(wait=False)


PROVIDERS: dict = {}  # model -> OpenRouter provider routing (EU pinning), filled from settings.providers


def openrouter_extra(base_url: str | None, extra: dict | None, model: str | None = None) -> dict | None:
    if base_url and "openrouter.ai" in base_url:
        extra = dict(extra or {})
        extra.setdefault("usage", {"include": True})
        if model and model in PROVIDERS and "provider" not in extra:
            extra["provider"] = PROVIDERS[model]
    return extra or None


class ImageNotSupported(Exception):
    """The selected model/endpoint does not accept image input."""


class LLM:
    def __init__(self, cfg: dict):
        if not cfg.get("base_url") or not cfg.get("model"):
            raise RuntimeError("Brak konfiguracji LLM: ustaw O2J_LLM_BASE_URL, O2J_LLM_API_KEY, O2J_LLM_MODEL (.env)")
        self.cfg = cfg
        self.model = cfg["model"]
        PROVIDERS.update(cfg.get("providers") or {})
        self.client = OpenAI(base_url=cfg["base_url"], api_key=cfg.get("api_key") or "none",
                             timeout=float(cfg.get("timeout", 180)), max_retries=0)  # retries: _chat (backoff)

    def _chat(self, messages, **kw):
        """One chat completion through o2j.api: global concurrency cap, backoff on 429/5xx/timeouts,
        FatalAPIError on a bad key / no credits."""
        model = kw.get("model", self.model)
        extra = openrouter_extra(self.cfg.get("base_url"), self.cfg.get("extra_body"), model)

        def call():
            r = self.client.chat.completions.create(model=model, messages=messages, extra_body=extra,
                                                    **{k: v for k, v in kw.items() if k != "model"})
            track(r)  # also the losing hedge request: it is billed
            return r
        try:
            return api.request(call, label=model, hedge_after=None if "timeout" in kw else self.cfg.get("hedge_after"))
        except api.FatalAPIError:
            raise
        except Exception as e:  # noqa: BLE001
            if api.status_of(e) in (400, 404) and "image" in str(e).lower():
                raise ImageNotSupported(str(e)) from e  # text-only model: no point retrying
            raise

    def extract_json(self, system: str, user: str, schema: dict | None, name: str = "extraction",
                     images: list[bytes] | None = None, model: str | None = None,
                     temperature: float | None = None, timeout: float | None = None) -> tuple[dict, dict]:
        """timeout: per-call budget for long generations (e.g. the doctype wizard); disables hedging."""
        kw = dict(temperature=self.cfg.get("temperature", 0) if temperature is None else temperature,
                  max_tokens=int(self.cfg.get("max_tokens", 4000)))
        if model:
            kw["model"] = model
        if timeout:
            kw["timeout"] = float(timeout)
        mode = self.cfg.get("structured_output", "json_schema")
        if schema is not None and mode == "json_schema":
            kw["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": name, "schema": schema, "strict": True}}
        elif mode in ("json_schema", "json_object"):
            kw["response_format"] = {"type": "json_object"}
        content = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": png_data_url(png)}} for png in images]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        last_err = None
        for attempt in range(3):  # empty / truncated / invalid JSON -> retry
            try:
                resp = self._chat(messages, **kw)
            except api.FatalAPIError:
                raise  # auth / billing: stops the batch
            except ImageNotSupported:
                # text-only model: drop attached page images and continue with the text layer / OCR text
                messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
                resp = self._chat(messages, **kw)
            except Exception as e:  # noqa: BLE001  provider may not support json_schema -> fall back
                if api.status_of(e) not in (400, 422) or kw.get("response_format", {}).get("type") == "json_object":
                    raise  # transient errors were already retried in api.request; do not double the load
                kw["response_format"] = {"type": "json_object"}
                resp = self._chat(messages, **kw)
            content = resp.choices[0].message.content or ""
            usage = resp.usage.model_dump() if resp.usage else {}
            try:
                return parse_json(content), {"model": resp.model, "usage": usage, "raw": content, "attempts": attempt + 1}
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
                if resp.choices[0].finish_reason == "length":
                    kw["max_tokens"] = int(kw["max_tokens"] * 2)
                kw["temperature"] = 0.2
        raise last_err

    def ocr(self, png: bytes, model: str | None = None, min_len: int = 40, attempts: int = 3) -> str:
        best = ""
        for _ in range(attempts):
            text = self._ocr_once(png, model)
            if len(text.strip()) > len(best.strip()):
                best = text
            if len(best.strip()) >= min_len:
                break
        return best

    def _ocr_once(self, png: bytes, model: str | None = None) -> str:
        resp = self._chat(
            [{"role": "user", "content": [
                {"type": "text", "text": "Przepisz dokładnie cały tekst z tej strony dokumentu (język polski). "
                                         "Zachowaj kolejność i podział na linie. Zwróć wyłącznie tekst."},
                {"type": "image_url", "image_url": {"url": png_data_url(png)}},
            ]}],
            model=model or self.model, temperature=0, max_tokens=4000,
        )
        return resp.choices[0].message.content or ""


def parse_json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r"^<think>.*?</think>", "", s, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1)
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start:end + 1]
    return json.loads(s)
