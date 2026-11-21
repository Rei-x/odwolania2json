"""Build a synthetic 'scanned' test set: rasterize training PDFs (no text layer), add rotation/noise/blur."""
import random
import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageFilter

src, dst, n = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 6
random.seed(0)
cases = sorted(p for p in src.iterdir() if p.is_dir())[::max(1, 60 // n)][:n]
for case in cases:
    (dst / case.name).mkdir(parents=True, exist_ok=True)
    for f in case.glob("*.pdf"):
        pdf = pdfium.PdfDocument(str(f))
        imgs = []
        for i in range(min(len(pdf), 4)):
            im = pdf[i].render(scale=150 / 72).to_pil().convert("L")
            im = im.rotate(random.uniform(-1.5, 1.5), expand=True, fillcolor=255)
            im = im.filter(ImageFilter.GaussianBlur(0.6))
            px = im.load()
            w, h = im.size
            for _ in range(w * h // 300):
                x, y = random.randrange(w), random.randrange(h)
                px[x, y] = random.choice((0, 90, 200))
            imgs.append(im.convert("RGB"))
        imgs[0].save(dst / case.name / f.name, save_all=True, append_images=imgs[1:], resolution=150)
        print(dst / case.name / f.name)
