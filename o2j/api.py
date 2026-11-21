"""Resilience shared by every LLM / OCR API request, in all worker threads:

- one global cap on requests in flight (all documents, all clients), so a batch never floods the provider;
- retries of transient failures (HTTP 408/409/425/429/5xx, timeouts, dropped connections) with exponential
  backoff and jitter, honouring `Retry-After` / `retry-after-ms`;
- after an HTTP 429 every thread pauses until the provider's cool-down ends (no thundering herd);
- auth / billing errors (401, 402) raise FatalAPIError at once: retrying cannot help, the batch stops.

Configured once from settings.yaml `llm:` (max_concurrency, retries, timeout_retries, backoff_base, backoff_cap).
"""
from __future__ import annotations

import email.utils
import random
import sys
import threading
import time

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529}
FATAL_STATUS = {401, 402}

_CFG = {"max_concurrency": 16, "retries": 5, "timeout_retries": 1, "backoff_base": 1.0, "backoff_cap": 30.0,
        "max_retry_after": 120.0}
_SLOTS = threading.BoundedSemaphore(_CFG["max_concurrency"])
_LOCK = threading.Lock()
_COOL_UNTIL = 0.0  # monotonic time until which nobody sends (set by a 429)
STATS = {"requests": 0, "retries": 0, "rate_limited": 0, "server_errors": 0, "timeouts": 0, "failed": 0}
QUIET = False  # tests: no retry log lines


class FatalAPIError(RuntimeError):
    """Wrong API key / no credits: no document can succeed, so the batch stops with this message."""


def configure(cfg: dict | None) -> None:
    """Apply `llm:` settings. Call before the workers start (the semaphore is replaced, not resized)."""
    global _SLOTS
    cfg = cfg or {}
    for k in ("max_concurrency", "retries", "timeout_retries"):
        if cfg.get(k) is not None:
            _CFG[k] = max(0, int(cfg[k]))
    for k in ("backoff_base", "backoff_cap", "max_retry_after"):
        if cfg.get(k) is not None:
            _CFG[k] = max(0.0, float(cfg[k]))
    _CFG["max_concurrency"] = max(1, _CFG["max_concurrency"])
    _SLOTS = threading.BoundedSemaphore(_CFG["max_concurrency"])


def settings() -> dict:
    return dict(_CFG)


def reset_stats() -> None:
    global _COOL_UNTIL
    with _LOCK:
        for k in STATS:
            STATS[k] = 0
        _COOL_UNTIL = 0.0


def status_of(e: BaseException) -> int | None:
    code = getattr(e, "status_code", None)
    return code if isinstance(code, int) else None


def is_timeout(e: BaseException) -> bool:
    import openai
    return isinstance(e, (openai.APITimeoutError, TimeoutError))


def is_fatal(e: BaseException) -> bool:
    return status_of(e) in FATAL_STATUS


def is_retryable(e: BaseException) -> bool:
    import openai
    code = status_of(e)
    if code is not None:
        return code in RETRYABLE_STATUS
    return isinstance(e, (openai.APITimeoutError, openai.APIConnectionError, TimeoutError, ConnectionError))


def retry_after(e: BaseException) -> float | None:
    """Seconds the provider asked us to wait (Retry-After: seconds or HTTP date; retry-after-ms)."""
    headers = getattr(getattr(e, "response", None), "headers", None)
    if not headers:
        return None
    try:
        ms = headers.get("retry-after-ms")
        if ms:
            return max(0.0, float(ms) / 1000)
        v = headers.get("retry-after")
        if not v:
            return None
        try:
            return max(0.0, float(v))
        except ValueError:
            dt = email.utils.parsedate_to_datetime(v)
            return max(0.0, dt.timestamp() - time.time())
    except Exception:  # noqa: BLE001  malformed header -> ordinary backoff
        return None


def backoff_delay(attempt: int, e: BaseException | None = None) -> float:
    """Retry-After when given (+ small jitter so waiting threads do not return in lockstep), otherwise
    exponential backoff with 'equal jitter': half fixed, half random, capped."""
    ra = retry_after(e) if e is not None else None
    if ra is not None:
        return min(ra, _CFG["max_retry_after"]) + random.uniform(0, 1.0)
    d = min(_CFG["backoff_cap"], _CFG["backoff_base"] * (2 ** attempt))
    return d / 2 + random.uniform(0, d / 2)


def _wait_cool_down() -> None:
    while True:
        with _LOCK:
            left = _COOL_UNTIL - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(left, 5.0))


def _short(e: BaseException) -> str:
    code = status_of(e)
    msg = str(e).replace("\n", " ")
    return (f"HTTP {code}: " if code else f"{type(e).__name__}: ") + msg[:160]


def describe_fatal(e: BaseException) -> str:
    code = status_of(e)
    if code == 401:
        why = "nieprawidłowy lub brakujący klucz API (HTTP 401) — sprawdź O2J_LLM_API_KEY w .env"
    elif code == 402:
        why = "brak środków na koncie dostawcy LLM (HTTP 402) — doładuj konto lub użyj innego klucza"
    else:
        why = f"dostawca LLM odrzucił żądanie ({_short(e)})"
    return why


def request(fn, *, label: str = "LLM", hedge_after: float | None = None, retries: int | None = None,
            timeout_retries: int | None = None):
    """fn() under the global concurrency cap, with retries. `hedge_after`: see llm.hedged (the duplicate
    request is not counted against the cap; at most a few run at once)."""
    from .llm import hedged
    retries = _CFG["retries"] if retries is None else int(retries)
    timeout_retries = _CFG["timeout_retries"] if timeout_retries is None else int(timeout_retries)
    attempt = timeouts = 0
    while True:
        _wait_cool_down()
        with _LOCK:
            STATS["requests"] += 1
        try:
            with _SLOTS:
                return hedged(fn, hedge_after)
        except Exception as e:  # noqa: BLE001
            if is_fatal(e):
                raise FatalAPIError(describe_fatal(e)) from e
            if not is_retryable(e):
                with _LOCK:
                    STATS["failed"] += 1
                raise
            code = status_of(e)
            if is_timeout(e):
                timeouts += 1
                give_up = timeouts > timeout_retries or attempt >= retries
            else:
                give_up = attempt >= retries
            with _LOCK:
                if is_timeout(e):
                    STATS["timeouts"] += 1
                elif code == 429:
                    STATS["rate_limited"] += 1
                elif code is not None and code >= 500:
                    STATS["server_errors"] += 1
                if give_up:
                    STATS["failed"] += 1
            if give_up:
                raise
            delay = backoff_delay(attempt, e)
            if code == 429:  # everybody waits: the provider is throttling the whole key, not this request
                global _COOL_UNTIL
                with _LOCK:
                    _COOL_UNTIL = max(_COOL_UNTIL, time.monotonic() + delay)
            with _LOCK:
                STATS["retries"] += 1
            if not QUIET:
                print(f"[api] {label}: {_short(e)} -> ponowienie {attempt + 1}/{retries} za {delay:.1f} s",
                      file=sys.stderr, flush=True)
            attempt += 1
            time.sleep(delay)
