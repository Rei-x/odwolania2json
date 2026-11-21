"""Thin client for any OpenAI-compatible chat API (open-weight models hosted by a provider)."""
from __future__ import annotations

import json
import re
import random
import time

from openai import OpenAI

from .pdf import png_data_url


class LLM:
    def __init__(self, cfg: dict):
        if not cfg.get("base_url") or not cfg.get("model"):
            raise RuntimeError("Brak konfiguracji LLM: ustaw O2J_LLM_BASE_URL, O2J_LLM_API_KEY, O2J_LLM_MODEL (.env)")
        self.cfg = cfg
        self.model = cfg["model"]
        self.client = OpenAI(base_url=cfg["base_url"], api_key=cfg.get("api_key") or "none",
                             timeout=float(cfg.get("timeout", 180)))

    def _chat(self, messages, **kw):
        last = None
        for attempt in range(int(self.cfg.get("retries", 2)) + 1):
            try:
                extra = self.cfg.get("extra_body") or None
                return self.client.chat.completions.create(model=kw.get("model", self.model), messages=messages,
                                                           extra_body=extra, **{k: v for k, v in kw.items() if k != "model"})
            except Exception as e:  # noqa: BLE001  (rate limits, timeouts, 5xx)
                if getattr(e, "status_code", None) in (401, 402, 403):
                    raise RuntimeError(f"LLM API odrzuciło żądanie (klucz/środki): {e}") from e
                last = e
                time.sleep(min(30, 2 ** attempt + random.random()))
        raise last

    def extract_json(self, system: str, user: str, schema: dict | None, name: str = "extraction",
                     images: list[bytes] | None = None) -> tuple[dict, dict]:
        kw = dict(temperature=self.cfg.get("temperature", 0), max_tokens=int(self.cfg.get("max_tokens", 4000)))
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
        try:
            resp = self._chat(messages, **kw)
        except Exception:  # provider may not support json_schema -> fall back
            kw["response_format"] = {"type": "json_object"}
            resp = self._chat(messages, **kw)
        content = resp.choices[0].message.content or ""
        usage = resp.usage.model_dump() if resp.usage else {}
        return parse_json(content), {"model": resp.model, "usage": usage, "raw": content}

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
