"""Build *hard* synthetic scan test sets: data/hard_scans/<variant>/<case>/<same filenames>.pdf

    python eval/make_hard_scans.py [--src data/train] [--dst data/hard_scans] [--cases przyklad_02,...] [--variants a,b]

Every variant except `mixed` produces image-only PDFs (first <=4 pages). `mixed` scans only page 1
(rendered with the `heavy_noise`-like degradation) and keeps the original text layer on the other pages.
Only Pillow / numpy / pypdfium2.
"""
from __future__ import annotations

import argparse
import io
import math
import random
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

DEFAULT_CASES = ["przyklad_02", "przyklad_14", "przyklad_26", "przyklad_38", "przyklad_50"]


def render(page, dpi=150) -> Image.Image:
    return page.render(scale=dpi / 72).to_pil().convert("RGB")


def _gray(im):
    return im.convert("L")


# ---------------------------------------------------------------- degradations (PIL RGB in -> PIL RGB out)
def low_dpi(page, rng):
    im = render(page, 90).convert("L").filter(ImageFilter.GaussianBlur(0.5))
    w, h = im.size
    return im.resize((int(w * 200 / 90), int(h * 200 / 90)), Image.BILINEAR).convert("RGB")


def heavy_noise(page, rng):
    a = np.asarray(_gray(render(page, 150)), dtype=np.float32)
    nr = np.random.default_rng(rng.randrange(1 << 30))
    a += nr.normal(0, 28, a.shape)  # speckle / gaussian
    m = nr.random(a.shape)
    a[m < 0.03] = 0  # pepper
    a[m > 0.97] = 255  # salt
    # blotchy speckles (dust)
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    w, h = im.size
    for _ in range(w * h // 4000):
        x, y, r = rng.randrange(w), rng.randrange(h), rng.choice((1, 1, 2, 3))
        d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice((0, 40, 80)))
    return im.filter(ImageFilter.GaussianBlur(0.4)).convert("RGB")


def rotated_5deg(page, rng):
    im = _gray(render(page, 150))
    ang = rng.choice((-1, 1)) * rng.uniform(4.5, 5.5)
    return im.rotate(ang, expand=True, fillcolor=255, resample=Image.BICUBIC).convert("RGB")


def rotated_90(page, rng):
    im = _gray(render(page, 150))
    return im.rotate(rng.choice((90, 180, 270)), expand=True, fillcolor=255).convert("RGB")


def _perspective_coeffs(src, dst):
    # solve for PIL's 8 coeffs mapping dst(output) -> src(input)
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def skew_perspective(page, rng):
    im = render(page, 150)
    w, h = im.size
    # pad (desk background), then warp corners
    pad = int(0.06 * w)
    bg = Image.new("RGB", (w + 2 * pad, h + 2 * pad), (95, 85, 75))
    bg.paste(im, (pad, pad))
    W, H = bg.size
    j = lambda s: rng.uniform(0, s)  # noqa: E731
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    dst = [(j(0.08 * W), j(0.05 * H)), (W - j(0.03 * W), j(0.02 * H)),
           (W - j(0.10 * W), H - j(0.04 * H)), (j(0.02 * W), H - j(0.02 * H))]
    out = bg.transform((W, H), Image.PERSPECTIVE, _perspective_coeffs(src, dst), Image.BICUBIC,
                       fillcolor=(60, 55, 50))
    # uneven lighting: diagonal gradient + soft shadow blob
    a = np.asarray(out, dtype=np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = rng.uniform(0, 2 * math.pi)
    g = (np.cos(ang) * xx / W + np.sin(ang) * yy / H)
    g = (g - g.min()) / (g.max() - g.min() + 1e-6)
    light = 0.55 + 0.45 * g
    cx, cy = rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.8) * H
    shadow = 1 - 0.35 * np.exp(-(((xx - cx) / (0.35 * W)) ** 2 + ((yy - cy) / (0.25 * H)) ** 2))
    a = a * (light * shadow)[..., None]
    a[..., 0] *= 1.04; a[..., 2] *= 0.9  # warm tint
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    return out


def jpeg_low(page, rng):
    im = render(page, 150)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=15)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")  # saved again as JPEG q15 below


def faded(page, rng):
    a = np.asarray(_gray(render(page, 150)), dtype=np.float32)
    a = 175 + a * (75 / 255)  # black -> ~175 (light grey), white -> 250
    nr = np.random.default_rng(rng.randrange(1 << 30))
    a += nr.normal(0, 4, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5)).convert("RGB")


def _stamp(rng, size, color):
    s = size
    st = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    c = color + (150,)
    d.ellipse((4, 4, s - 4, s - 4), outline=c, width=max(3, s // 40))
    d.ellipse((s // 6, s // 6, s - s // 6, s - s // 6), outline=c, width=max(2, s // 70))
    # text-like strokes around the ring and in the middle
    for k in range(24):
        t = 2 * math.pi * k / 24
        r1, r2 = s * 0.36, s * 0.44
        x1, y1 = s / 2 + r1 * math.cos(t), s / 2 + r1 * math.sin(t)
        x2, y2 = s / 2 + r2 * math.cos(t + 0.08), s / 2 + r2 * math.sin(t + 0.08)
        d.line((x1, y1, x2, y2), fill=c, width=max(2, s // 80))
    d.rectangle((s * 0.3, s * 0.45, s * 0.7, s * 0.55), outline=c, width=max(2, s // 80))
    return st.rotate(rng.uniform(-30, 30), resample=Image.BICUBIC)


def _scribble(rng, w, h):
    sc = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(sc)
    col = rng.choice([(20, 30, 140, 230), (10, 10, 10, 230)])
    pts, x, y = [], 0.05 * w, h * 0.5
    for i in range(60):
        x += rng.uniform(0.005, 0.03) * w
        y = h * 0.5 + math.sin(i * rng.uniform(0.6, 1.4)) * h * rng.uniform(0.15, 0.45)
        pts.append((min(x, w - 2), y))
    d.line(pts, fill=col, width=3, joint="curve")
    d.line([(0.1 * w, 0.7 * h), (0.9 * w, 0.55 * h)], fill=col, width=2)
    return sc


def stamp_overlay(page, rng):
    im = render(page, 150).convert("RGBA")
    w, h = im.size
    for _ in range(2):
        col = rng.choice([(200, 30, 40), (30, 60, 190), (120, 40, 160)])
        s = int(w * rng.uniform(0.22, 0.32))
        st = _stamp(rng, s, col)
        im.alpha_composite(st, (rng.randrange(0, w - s), rng.randrange(int(0.05 * h), int(0.6 * h))))
    sw, sh = int(w * 0.4), int(h * 0.08)
    sig = _scribble(rng, sw, sh)
    im.alpha_composite(sig, (rng.randrange(0, w - sw), rng.randrange(int(0.15 * h), int(0.75 * h))))
    sig2 = _scribble(rng, sw, sh)
    im.alpha_composite(sig2, (rng.randrange(0, w - sw), rng.randrange(int(0.6 * h), h - sh)))
    return im.convert("RGB")


VARIANTS = {f.__name__: f for f in (low_dpi, heavy_noise, rotated_5deg, rotated_90, skew_perspective, jpeg_low,
                                     faded, stamp_overlay)}
ALL = list(VARIANTS) + ["mixed"]


def write_image_pdf(imgs: list[Image.Image], out: Path, jpeg_q: int | None = None):
    if jpeg_q:
        # Pillow's PDF writer stores RGB images as JPEG; force low quality by pre-encoding
        imgs[0].save(out, save_all=True, append_images=imgs[1:], resolution=150, quality=jpeg_q)
    else:
        imgs[0].save(out, save_all=True, append_images=imgs[1:], resolution=150)


def make_mixed(src: Path, out: Path, rng):
    pdf = pdfium.PdfDocument(str(src))
    img = heavy_noise(pdf[0], rng)
    w_pt, h_pt = pdf.get_page_size(0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    buf.seek(0)
    page = pdf.new_page(w_pt, h_pt, index=0)
    pi = pdfium.PdfImage.new(pdf)
    pi.load_jpeg(buf, inline=True)
    pi.set_matrix(pdfium.PdfMatrix().scale(w_pt, h_pt))
    page.insert_obj(pi)
    page.gen_content()
    pdf.del_page(1)  # drop original page 1 (text layer)
    pdf.save(str(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path("data/train"))
    ap.add_argument("--dst", type=Path, default=Path("data/hard_scans"))
    ap.add_argument("--cases", default=",".join(DEFAULT_CASES))
    ap.add_argument("--variants", default=",".join(ALL))
    a = ap.parse_args()
    for var in a.variants.split(","):
        rng = random.Random(f"{var}-0")
        for case in a.cases.split(","):
            d = a.dst / var / case
            d.mkdir(parents=True, exist_ok=True)
            for f in sorted((a.src / case).glob("*.pdf")):
                if var == "mixed":
                    make_mixed(f, d / f.name, rng)
                else:
                    pdf = pdfium.PdfDocument(str(f))
                    imgs = [VARIANTS[var](pdf[i], rng) for i in range(min(len(pdf), 4))]
                    write_image_pdf(imgs, d / f.name, jpeg_q=15 if var == "jpeg_low" else None)
                print(d / f.name)


if __name__ == "__main__":
    main()
