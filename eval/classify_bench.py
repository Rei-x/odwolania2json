"""Classification benchmark: training PDFs + blind set (filename hidden) + out-of-scope negatives.

Uses classification settings of the active profile, incl. skip_llm_margin (--no-skip: always ask the LLM)."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from o2j import pdf as P  # noqa: E402
from o2j.classify import classify  # noqa: E402
from o2j.llm import COST  # noqa: E402
from o2j.pipeline import Pipeline  # noqa: E402

TRUTH = {"odwolanie.pdf": "odwolanie", "pelnomocnictwo.pdf": "pelnomocnictwo", "potwierdzenie_przelewu.pdf": "przelew",
         "przelew.pdf": "przelew"}


def main(neg_dir: str | None = None, skip: bool = True):
    pipe = Pipeline()
    items = [(f, TRUTH.get(f.name, "inny")) for f in sorted((ROOT / "data/train").glob("*/*.pdf"))]  # others = negatives
    items += [(f, "inny" if "negatyw" in f.parent.name else TRUTH.get(f.name, "inny"))
              for f in sorted((ROOT / "data/blind").glob("*/*.pdf"))]
    if neg_dir:
        items += [(f, "inny") for f in sorted(Path(neg_dir).glob("*")) if f.suffix.lower() in P.SUPPORTED_EXT]

    def one(it):
        f, t = it
        doc = P.load(f, ocr=pipe._ocr, ocr_max_pages=1)
        c = pipe.s.get("classification", {})
        typ, info = classify(doc.text(), Path("dokument.pdf"), pipe.specs, pipe.llm, 3,
                             c.get("mode", "llm_confirm"), model=c.get("model"), vote_models=c.get("vote_models"),
                             skip_llm_margin=c.get("skip_llm_margin") if skip else None)
        return f, t, typ, bool(info.get("llm_skipped"))

    res = list(ThreadPoolExecutor(16).map(one, items))
    bad = [(str(f.relative_to(ROOT)) if ROOT in f.parents else f.name, t, typ) for f, t, typ, _ in res if t != typ]
    print(f"model={pipe.llm.model} total={len(res)} wrong={len(bad)} llm_skipped={sum(r[3] for r in res)} "
          f"cost=${COST['usd']:.4f}")
    for b in bad:
        print("  WRONG", *b)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-skip"]
    main(args[0] if args else None, skip="--no-skip" not in sys.argv)
