"""Pluggable OCR engines (selected in config/settings.yaml -> ocr.engine).

- vlm:    vision-language model behind an OpenAI-compatible API
- paddle: PaddleOCR-VL-1.6 (open-source SOTA document OCR, runs locally on CPU)
- none:   no OCR
"""
from __future__ import annotations

import io
import threading

from openai import OpenAI

from .pdf import png_data_url

OCR_PROMPT = ("Przepisz dokładnie cały tekst z tej strony dokumentu (język polski), od pierwszej do ostatniej linii, "
              "łącznie z nagłówkami, podpisami i stopkami. Zachowaj kolejność i podział na linie, polskie znaki "
              "diakrytyczne oraz wszystkie cyfry. Niczego nie poprawiaj ani nie pomijaj — przepisuj litera po literze, także nazwiska bez polskich znaków (np. 'Szymanski' zostaje 'Szymanski'). Zwróć wyłącznie tekst.")


class VlmOCR:
    def __init__(self, cfg: dict, llm_cfg: dict):
        self.model = cfg.get("model") or llm_cfg["model"]
        self.client = OpenAI(base_url=cfg.get("base_url") or llm_cfg["base_url"],
                             api_key=cfg.get("api_key") or llm_cfg.get("api_key") or "none",
                             timeout=float(cfg.get("timeout", 300)))
        self.max_tokens = int(cfg.get("max_tokens", 16000))
        self.extra = {}
        if cfg.get("reasoning") == "off":
            self.extra["reasoning"] = {"enabled": False}
        elif cfg.get("reasoning"):
            self.extra["reasoning"] = {"effort": cfg["reasoning"]}

    def __call__(self, png: bytes) -> str:
        best = ""
        for _ in range(3):
            try:
                r = self.client.chat.completions.create(
                    model=self.model, temperature=0, max_tokens=self.max_tokens, extra_body=self.extra or None,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": png_data_url(png)}}]}])
            except Exception:  # noqa: BLE001
                continue
            c = r.choices[0]
            text = c.message.content or ""
            if len(text) > len(best):
                best = text
            if c.finish_reason != "length" and len(best.strip()) > 40:
                break
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


def make_engine(cfg: dict, llm_cfg: dict):
    eng = (cfg or {}).get("engine", "vlm")
    if eng == "vlm":
        return VlmOCR(cfg, llm_cfg)
    if eng == "paddle":
        return PaddleOCRVL(cfg)
    return None
