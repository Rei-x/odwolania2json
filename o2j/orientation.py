"""Document orientation (0/90/180/270) with PP-LCNet_x1_0_doc_ori (PaddleOCR, Apache-2.0, 7 MB ONNX, CPU).

Weights: models/PP-LCNet_x1_0_doc_ori.onnx (downloaded on first use from the Hugging Face mirror
monkt/paddleocr-onnx if missing).
"""
from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = Path(__file__).resolve().parent.parent / "models" / "PP-LCNet_x1_0_doc_ori.onnx"
URL = ("https://huggingface.co/monkt/paddleocr-onnx/resolve/main/preprocessing/doc-orientation/"
       "PP-LCNet_x1_0_doc_ori.onnx")
_SESSION = None
_LOCK = threading.Lock()
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _session():
    global _SESSION
    with _LOCK:
        if _SESSION is None:
            import onnxruntime as ort
            if not MODEL.exists():
                MODEL.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(URL, MODEL)
            _SESSION = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _SESSION


def _prep(im: Image.Image) -> np.ndarray:
    im = im.convert("RGB")
    w, h = im.size
    s = 256 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BILINEAR)
    w, h = im.size
    l, t = (w - 224) // 2, (h - 224) // 2
    a = np.asarray(im.crop((l, t, l + 224, t + 224)), dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return a.transpose(2, 0, 1)[None]


def predict(im: Image.Image) -> tuple[int, float]:
    """Returns (angle the page is rotated by, probability). angle in {0, 90, 180, 270}."""
    out = _session().run(None, {"x": _prep(im)})[0][0].astype(np.float64)
    if abs(out.sum() - 1.0) < 1e-3 and out.min() >= 0:  # exported model already ends with softmax
        p = out
    else:
        p = np.exp(out - out.max())
        p /= p.sum()
    k = int(p.argmax())
    return k * 90, float(p[k])


def correct(im: Image.Image, min_prob: float = 0.6) -> tuple[Image.Image, int, float]:
    angle, prob = predict(im)
    if angle == 0 or prob < min_prob:
        return im, 0, prob
    return im.rotate(angle, expand=True), angle, prob   # PIL rotates counter-clockwise
