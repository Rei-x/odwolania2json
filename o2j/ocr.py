"""Pluggable OCR engines (selected in config/settings.yaml -> ocr.engine).

- vlm:    vision-language model behind an OpenAI-compatible API
- paddle: PaddleOCR-VL-1.6 (open-source SOTA document OCR, runs locally on CPU)
- none:   no OCR
"""
from __future__ import annotations

import io
import random
import re
import sys
import threading
import time

from openai import OpenAI

from .llm import hedged, openrouter_extra, track
from .pdf import png_data_url

OCR_PROMPT = ("Przepisz dokładnie cały tekst z tej strony dokumentu (język polski), od pierwszej do ostatniej linii, "
              "łącznie z nagłówkami, podpisami i stopkami. Zachowaj kolejność i podział na linie, polskie znaki "
              "diakrytyczne oraz wszystkie cyfry. Niczego nie poprawiaj ani nie pomijaj — przepisuj litera po literze, także nazwiska bez polskich znaków (np. 'Szymanski' zostaje 'Szymanski'). Zwróć wyłącznie tekst.")


ANTI_LOOP = (" Linie separatorów (kreski, kropki, podkreślenia) zapisz jako '---'. Nigdy nie powtarzaj tego samego "
             "fragmentu wielokrotnie.")


def collapse(text: str) -> str:
    """Collapse degenerate repetitions (e.g. thousands of '- - -' from dashed rules)."""
    text = re.sub(r"((?:\S{1,4}\s?))\1{15,}", lambda m: m.group(1) * 3, text)
    return re.sub(r"(.{5,80}?)\1{4,}", r"\1", text, flags=re.S)


def degenerate(text: str) -> bool:
    c = collapse(text)
    return len(text) - len(c) > 1500 or (len(text) > 200 and len(c) < 0.7 * len(text))


class FatalAPIError(RuntimeError):
    """Auth / billing errors: retrying cannot help, surface them."""


def _fatal(e: Exception) -> bool:
    code = getattr(e, "status_code", None)
    return code in (401, 402, 403)


class VlmOCR:
    _slots: threading.BoundedSemaphore | None = None  # page requests in flight, shared by all documents
    _slots_lock = threading.Lock()

    def __init__(self, cfg: dict, llm_cfg: dict):
        self.model = cfg.get("model") or llm_cfg["model"]
        self.client = OpenAI(base_url=cfg.get("base_url") or llm_cfg["base_url"],
                             api_key=cfg.get("api_key") or llm_cfg.get("api_key") or "none",
                             timeout=float(cfg.get("timeout", 300)), max_retries=0)
        self.timeout = float(cfg.get("timeout", 300))
        self.attempts = max(1, int(cfg.get("attempts", 4)))
        self.hedge_after = cfg.get("hedge_after")  # seconds without an answer before a duplicate request
        with VlmOCR._slots_lock:  # batch runs: pages wait here (not in the provider queue, where the timeout ticks)
            if VlmOCR._slots is None:
                VlmOCR._slots = threading.BoundedSemaphore(max(1, int(cfg.get("max_concurrency", 12))))
        self.max_tokens = int(cfg.get("max_tokens", 16000))
        self.base_url = cfg.get("base_url") or llm_cfg["base_url"]
        self.extra = {}
        if cfg.get("reasoning") == "off":
            self.extra["reasoning"] = {"effort": "none"}  # {"enabled": False} is ignored by some models
        elif cfg.get("reasoning"):
            self.extra["reasoning"] = {"effort": cfg["reasoning"]}

    def __call__(self, png: bytes) -> str:
        best, prompt = "", OCR_PROMPT
        for attempt in range(self.attempts):
            # the last attempt gets a double budget: a page without text is worse than a slow page
            last = attempt == self.attempts - 1 and attempt > 0
            client = self.client.with_options(timeout=2 * self.timeout) if last else self.client

            def call(prompt=prompt, temp=0 if attempt == 0 else 0.2, client=client):
                resp = client.chat.completions.create(
                    model=self.model, temperature=temp, max_tokens=self.max_tokens,
                    extra_body=openrouter_extra(self.base_url, self.extra, self.model),
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": png_data_url(png)}}]}])
                track(resp)  # also the losing hedge request: it is billed
                return resp
            try:
                with VlmOCR._slots:
                    r = hedged(call, self.hedge_after)
            except Exception as e:  # noqa: BLE001
                if _fatal(e):
                    raise FatalAPIError(f"OCR API: {e}") from e
                print(f"[ocr] attempt {attempt + 1} failed: {e!r}", file=sys.stderr)
                time.sleep(min(8.0, 2 ** attempt + random.random()))  # rate limit / 5xx: short backoff
                continue
            c = r.choices[0]
            text = c.message.content or ""
            bad = c.finish_reason == "length" or degenerate(text)
            text = collapse(text)
            if len(text.strip()) > len(best.strip()) and not (bad and best):
                best = text
            if not bad and len(best.strip()) > 40:
                break
            prompt = OCR_PROMPT + ANTI_LOOP
        return best


class PaddleOCRVL:
    _lock = threading.Lock()
    _pipe = None

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def _pipeline(self):
        if PaddleOCRVL._pipe is None:
            from paddleocr import PaddleOCRVL as P  # optional dependency (requirements-ocr.txt)
            kw = {"device": self.cfg.get("device", "cpu")}
            if self.cfg.get("paddle_model"):
                kw["pipeline_version"] = self.cfg["paddle_model"]
            PaddleOCRVL._pipe = P(**kw)
        return PaddleOCRVL._pipe

    def __call__(self, png: bytes) -> str:
        import numpy as np
        from PIL import Image
        img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))[:, :, ::-1]  # BGR
        with PaddleOCRVL._lock:  # model is not thread-safe; serialise
            out = list(self._pipeline().predict(img))
        parts = []
        for res in out:
            j = res.json if isinstance(res.json, dict) else {}
            blocks = (j.get("res") or j).get("parsing_res_list") or []
            for b in blocks:
                txt = b.get("block_content") or b.get("content") or ""
                if txt.strip():
                    parts.append(txt.strip())
            if not blocks:
                md = getattr(res, "markdown", None)
                if isinstance(md, dict):
                    parts.append(md.get("markdown_texts", ""))
        return "\n".join(parts)


class RapidOCREngine:
    """Local CPU OCR (RapidOCR / PP-OCRv5 latin, ONNX) — no API, not an LLM. Weaker on Polish diacritics
    than a VLM, but free, offline and fast enough for a laptop (~3-7 s/page on 4 cores)."""
    _lock = threading.Lock()
    _eng = None

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def __call__(self, png: bytes) -> str:
        from PIL import Image
        with RapidOCREngine._lock:
            if RapidOCREngine._eng is None:
                from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR  # optional: pip install rapidocr
                RapidOCREngine._eng = RapidOCR(params={"Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5,
                                                       "Rec.model_type": ModelType.MOBILE})
            r = RapidOCREngine._eng(Image.open(io.BytesIO(png)).convert("RGB"))
        return "\n".join(r.txts) if r and r.txts else ""


def make_engine(cfg: dict, llm_cfg: dict):
    eng = (cfg or {}).get("engine", "vlm")
    if eng == "vlm":
        return VlmOCR(cfg, llm_cfg)
    if eng == "paddle":
        return PaddleOCRVL(cfg)
    if eng == "rapidocr":
        return RapidOCREngine(cfg)
    return None
