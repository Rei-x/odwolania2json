"""Classification benchmark: 180 training PDFs (filename hidden) + out-of-scope negatives."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from o2j import pdf as P  # noqa: E402
from o2j.classify import classify  # noqa: E402
from o2j.llm import COST  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

TRUTH = {"odwolanie.pdf": "odwolanie", "pelnomocnictwo.pdf": "pelnomocnictwo", "potwierdzenie_przelewu.pdf": "przelew"}


def main(neg_dir: str | None = None):
    pipe = Pipeline()
    items = [(f, TRUTH[f.name]) for f in sorted((ROOT / "data/train").glob("*/*.pdf"))]
    if neg_dir:
        items += [(f, "inny") for f in sorted(Path(neg_dir).glob("*")) if f.suffix.lower() in P.SUPPORTED_EXT]

    def one(it):
        f, t = it
        doc = P.load(f, ocr=pipe._ocr, ocr_max_pages=1)
        typ, info = classify(doc.text(), Path("dokument.pdf"), pipe.specs, pipe.llm, 3,
                             pipe.s.get("classification", {}).get("mode", "llm_confirm"))
        return f, t, typ

    res = list(ThreadPoolExecutor(16).map(one, items))
    bad = [(str(f.relative_to(ROOT)) if ROOT in f.parents else f.name, t, typ) for f, t, typ in res if t != typ]
    print(f"model={pipe.llm.model} total={len(res)} wrong={len(bad)} cost=${COST['usd']:.4f}")
    for b in bad:
        print("  WRONG", *b)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
