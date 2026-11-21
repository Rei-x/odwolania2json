# Blind test set (frozen)

20 synthetic cases (`blind_01` … `blind_20`), 3 documents each (60 PDFs), in the same layout as
`data/train/przyklad_NN/`: `odwolanie.pdf`, `pelnomocnictwo.pdf`, `potwierdzenie_przelewu.pdf` plus
ground truth `odwolanie.json`, `pelnomocnictwo.json`, `przelew.json`.

`blind_negatywne/` holds 3 realistic out-of-scope documents (as in `data/train/negatywne/`). Each one's
expected output is `{}`, in a JSON file named after the PDF stem.

`czynnosc_opis` labels follow the official dictionary `data/schemas/czynnosc_powod_id_dict.md`
(e.g. 6 = "Odpowiedzi/wyjaśnienia do SWZ"). Reason 12 ("Projektowane postanowienia umowy") also occurs.

**This set is for final evaluation only.** Do not open the PDFs, the JSONs, `_manifest.json` or
`_build/`, and do not tune the pipeline on per-field errors from this set. Look only at the aggregate
numbers printed by `eval/run_blind.py`.

## How it was generated

`python -m eval.make_blind` (seed `20261121`, generator model `moonshotai/kimi-k3.1-pro`):

1. Each case is derived from one training case that `eval/make_variants.py` does **not** use.
   It keeps the source case's *structure*: the type of the first contested act, the number of attorneys,
   consortium / several contracting authorities / sole trader, and whether a header date and BZP/TED
   numbers are present.
2. All *facts* are drawn again: company and public-body names, people, KRS/NIP/REGON/PESEL (999-prefixed,
   with valid checksums), IBAN accounts, dates, procedure numbers, titles, amounts, transfer titles.
3. Each case gets 1–3 seeded difficulties from a broad pool (layout, notation, structure, distractors,
   document length, bank layouts and so on). Each document also gets a random baseline style: law-firm
   phrasing, header format, bank profile, fonts, margins and page numbering.
4. The ground truth is built by code from the facts, following the schema comments and the training
   conventions. The LLM never writes the GT.
5. The LLM writes each document from scratch from the facts, the GT and the layout instructions. The
   source training document is used only as a genre example. The result is rendered to PDF with reportlab.
6. Verification: automatic checks that every GT value and every exact required string is in the text,
   that null fields are absent, and that there are no identifiers, dates or source-case names that were
   not given. Failed documents were regenerated with feedback. Every case was then also read manually
   (pdftotext).

## Evaluation

```bash
.venv/bin/python -m eval.run_blind            # prints overall F1, per-doctype F1, cost only
.venv/bin/python -m eval.run_blind --details  # also per-field errors (breaks blindness; avoid)
```

Out-of-scope documents are scored as in the organiser's metric: any field extracted from them counts as
an FP, and a correct `{}` adds no counts. The script also prints how many of them correctly returned `{}`.

Options: `--workers N`, `--model M`, `--out DIR`. The blind cases are not in `data/train`, so no
few-shot exclusion is needed. Without `--details`, only `summary.json` is kept in the run directory.
