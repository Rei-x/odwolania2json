"""Prototype: OCR wrapper that detects degenerate output (repetition loops, e.g. dashed separator lines rendered
as thousands of '- - -') and re-OCRs with an anti-loop prompt; collapses residual runs.

    from eval.ocr_robust import RobustOCR; engine = RobustOCR(base_vlm_engine)
"""
from __future__ import annotations

import re

ANTI_LOOP = (" Linie dekoracyjne/separatory (kreski, kropki, podkreślenia) zapisz jako pojedyncze '---'. "
             "Nie powtarzaj żadnego znaku ani frazy więcej niż kilka razy.")

_RUN = re.compile(r"((?:\S{1,4}\s?))\1{15,}")  # same short token repeated 16+ times


def collapse(text: str) -> str:
    return _RUN.sub(lambda m: m.group(1).strip() * 3 + " ", text)


def degenerate(text: str) -> bool:
    if not text.strip():
        return True
    removed = len(text) - len(collapse(text))
    return removed > 0.3 * len(text) or removed > 1500


class RobustOCR:
    def __init__(self, base):
        self.base = base

    def __call__(self, png: bytes) -> str:
        from o2j import ocr as O
        t = self.base(png)
        if not degenerate(t):
            return collapse(t)
        orig = O.OCR_PROMPT
        try:
            O.OCR_PROMPT = orig + ANTI_LOOP
            t2 = self.base(png)
        finally:
            O.OCR_PROMPT = orig
        c1, c2 = collapse(t), collapse(t2)
        return c2 if len(c2) >= len(c1) else c1
