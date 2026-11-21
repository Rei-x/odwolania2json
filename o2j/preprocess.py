"""Page-image preprocessing before OCR (config: ocr.preprocess) (Pillow + numpy only).

Steps (applied in the given order):
  flat    - flat-field illumination correction (divide by blurred background) + autocontrast; fixes shadows,
            uneven lighting, faded/low-contrast scans. Output is grayscale.
  orient  - coarse 0/90/180/270 orientation from projection profiles (0 vs 90) + ascender/descender asymmetry
            (0 vs 180).
  deskew  - small-angle deskew (+-8 deg) maximising the variance of the horizontal projection profile.
  up      - upscale small renders so the long side is >= 2400 px.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def _to_png(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def flat(im: Image.Image) -> Image.Image:
    g = im.convert("L")
    w, h = g.size
    small = g.resize((max(1, w // 8), max(1, h // 8)), Image.BILINEAR)
    bg = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.BILINEAR)
    a = np.asarray(g, np.float32) / np.maximum(np.asarray(bg, np.float32), 1) * 255
    a = np.clip(a, 0, 255).astype(np.uint8)
    out = Image.fromarray(a)
    # stretch so that the darkest ink becomes black (faded scans)
    lo = np.percentile(a, 0.5)
    if lo > 40:
        out = out.point(lambda v: 0 if v <= lo else min(255, int((v - lo) * 255 / max(1, 245 - lo))))
    return ImageOps.autocontrast(out, cutoff=0.5)


def _ink(im: Image.Image, maxside=900) -> np.ndarray:
    g = im.convert("L")
    s = maxside / max(g.size)
    if s < 1:
        g = g.resize((int(g.width * s), int(g.height * s)), Image.BILINEAR)
    a = np.asarray(g, np.float32)
    thr = min(160, np.percentile(a, 5) + 0.5 * (np.median(a) - np.percentile(a, 5)))
    return (a < thr).astype(np.float32)


def _score(ink: np.ndarray) -> float:
    return float(np.var(ink.sum(axis=1)))


def deskew(im: Image.Image) -> Image.Image:
    ink = Image.fromarray((_ink(im) * 255).astype(np.uint8))
    best, best_a = -1.0, 0.0
    for a in np.arange(-8, 8.01, 0.5):
        s = _score(np.asarray(ink.rotate(a, expand=False, fillcolor=0), np.float32))
        if s > best:
            best, best_a = s, a
    for a in np.arange(best_a - 0.5, best_a + 0.51, 0.1):
        s = _score(np.asarray(ink.rotate(a, expand=False, fillcolor=0), np.float32))
        if s > best:
            best, best_a = s, a
    if abs(best_a) < 0.2:
        return im
    fill = 255 if im.mode == "L" else (255, 255, 255)
    return im.rotate(best_a, expand=True, fillcolor=fill, resample=Image.BICUBIC)


def _upright_score(ink: np.ndarray) -> float:
    """Latin/Polish text: within each text line the ink above the x-height band (ascenders, capitals, accents)
    outweighs the ink below it (descenders). Positive -> upright, negative -> upside down."""
    prof = ink.sum(axis=1)
    n = len(prof)
    on = prof > 0.01 * ink.shape[1]
    tot, i = 0.0, 0
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j < n and on[j]:
            j += 1
        seg = prof[i:j]
        if j - i >= 6 and seg.sum() > 0:
            band = np.where(seg > 0.5 * seg.max())[0]
            tot += seg[:band[0]].sum() - seg[band[-1] + 1:].sum()
        i = j
    return tot / (prof.sum() + 1e-6)


def orient(im: Image.Image) -> Image.Image:
    g = im.convert("L").filter(ImageFilter.MedianFilter(3))
    w, h = g.size
    g = g.crop((int(0.1 * w), int(0.1 * h), int(0.9 * w), int(0.9 * h)))  # drop dark borders / desk
    ink = _ink(g, maxside=2000)
    # 0 vs 90: text lines -> strong row-profile variance; compare best-deskew-ish in both orientations
    rows, cols = np.var(ink.sum(axis=1)) / ink.shape[1], np.var(ink.sum(axis=0)) / ink.shape[0]
    rot = 0
    if cols > 1.3 * rows:
        # rotated 90 or 270: try both, choose the more upright
        a90 = np.rot90(ink, 1)   # counter-clockwise
        a270 = np.rot90(ink, 3)
        rot = 90 if _upright_score(a90) >= _upright_score(a270) else 270
    else:
        if _upright_score(np.rot90(ink, 2)) > _upright_score(ink):
            rot = 180
    if rot == 0:
        return im
    return im.rotate(rot, expand=True)


def denoise(im: Image.Image) -> Image.Image:
    """Median filter only when the page is speckled (many isolated dark pixels on the background)."""
    g = im.convert("L")
    a = np.asarray(g, np.int16)
    m = np.asarray(g.filter(ImageFilter.MedianFilter(3)), np.int16)
    speck = float(((a < 128) & (m > 200)).mean())
    return g.filter(ImageFilter.MedianFilter(3)) if speck > 0.002 else im


def up(im: Image.Image) -> Image.Image:
    s = 2400 / max(im.size)
    if s <= 1.05:
        return im
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


STEPS = {"denoise": denoise, "flat": flat, "orient": orient, "deskew": deskew, "up": up}


def apply(steps, im: Image.Image) -> Image.Image:
    for s in steps:
        im = STEPS[s](im)
    return im


def make_render(steps, orig_render):
    def render_png(page, dpi=200):
        im = Image.open(io.BytesIO(orig_render(page, dpi)))
        return _to_png(apply(steps, im))
    return render_png


def png_steps(steps, png: bytes) -> bytes:
    if not steps:
        return png
    return _to_png(apply(steps, Image.open(io.BytesIO(png))))
