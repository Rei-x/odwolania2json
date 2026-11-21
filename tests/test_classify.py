"""Rule-based classification (o2j.classify.rule_scores / classify).

What is asserted:
- Every reference document in data/train/przyklad_*/ (odwolanie / pelnomocnictwo / przelew /
  potwierdzenie_przelewu) is classified correctly from its TEXT ONLY: the file is presented under the
  neutral name "dokument.pdf", the expected class wins with score >= min_score (3) and a margin >= 2,
  i.e. it is "confident" under the same rule classify() uses.
- Negative documents (data/train/negatywne/*.pdf) must NOT be rule-confident for any class, so that
  in the default llm_confirm mode the LLM decides (and can answer "inny"). Two known exceptions score as
  a confident "odwolanie" by rules alone (a KIO judgment and a presentation about appeal proceedings);
  they are xfail(strict) so a rules change that fixes them is noticed. They are only resolved correctly
  by the LLM path; with mode=rules they would be mislabelled.
- With an LLM stub answering "inny", negatives end up "inny"; with an LLM stub that raises, a
  non-confident document falls back to "inny".
"""
from pathlib import Path

import pytest
from conftest import TRAIN

from o2j import pdf as P
from o2j.classify import _despace, classify, rule_scores

MIN_SCORE = 3
EXPECTED = {"odwolanie.pdf": "odwolanie", "pelnomocnictwo.pdf": "pelnomocnictwo",
            "przelew.pdf": "przelew", "potwierdzenie_przelewu.pdf": "przelew"}
REFERENCE_DOCS = sorted(f for f in TRAIN.glob("przyklad_*/*.pdf") if f.name in EXPECTED)
NEGATIVES = sorted(TRAIN.glob("negatywne/*.pdf"))
NEG_RULE_CONFIDENT = {"KIO_KIO 2617-21.pdf", "2020_03_21-22prowadzenie_postepowania_odwolawczego.pdf"}


def _head(path: Path) -> str:
    return P.load(path).text()[:6000]


def _confident(scores):
    ranked = sorted(scores.values(), reverse=True)
    return ranked[0] >= MIN_SCORE and ranked[0] - ranked[1] >= 2


def test_training_data_present():
    assert len(REFERENCE_DOCS) >= 150
    assert NEGATIVES


@pytest.mark.parametrize("path", REFERENCE_DOCS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_reference_docs_classified_by_text(specs, path):
    scores = rule_scores(_head(path), "dokument.pdf", specs)
    best = max(scores, key=scores.get)
    assert best == EXPECTED[path.name], scores
    assert _confident(scores), scores


@pytest.mark.parametrize("path", [
    pytest.param(p, marks=pytest.mark.xfail(reason="rule-confident 'odwolanie' on a non-appeal doc; only the LLM "
                                                   "path (llm_confirm) rejects it"))
    if p.name in NEG_RULE_CONFIDENT else p for p in NEGATIVES
], ids=lambda p: p.name)
def test_negatives_not_rule_confident(specs, path):
    scores = rule_scores(_head(path), "dokument.pdf", specs)
    assert not _confident(scores), scores


class _LLM:
    def __init__(self, answer=None, exc=None):
        self.answer, self.exc, self.calls = answer, exc, 0

    def extract_json(self, system, user, schema, name=None, images=None):
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"typ": self.answer}, {}


@pytest.mark.parametrize("path", NEGATIVES, ids=lambda p: p.name)
def test_negatives_rejected_by_llm_path(specs, path):
    text = _head(path)
    llm = _LLM("inny")
    typ, info = classify(text, Path("dokument.pdf"), specs, llm)
    if text.strip():
        assert typ == "inny" and llm.calls == 1
    else:  # no text layer: nothing to show the LLM, decided by filename only (neutral -> inny)
        assert typ == "inny" and llm.calls == 0


def test_llm_failure_falls_back_to_confident_rules_or_inny(specs):
    llm = _LLM(exc=RuntimeError("offline"))
    typ, info = classify("PEŁNOMOCNICTWO\nMocodawca udziela pełnomocnictwa", Path("x.pdf"), specs, llm)
    assert typ == "pelnomocnictwo" and "llm_error" in info
    typ, _ = classify("Jakiś przelew bankowy", Path("x.pdf"), specs, llm)
    assert typ == "inny"


def test_rules_mode_skips_llm_when_confident(specs):
    llm = _LLM("inny")
    typ, info = classify("PEŁNOMOCNICTWO\nMocodawca udziela pełnomocnictwa", Path("x.pdf"), specs, llm, mode="rules")
    assert typ == "pelnomocnictwo" and llm.calls == 0 and info["method"] == "rules"


def test_despace_letter_spaced_heading():
    assert _despace("P E Ł N O M O C N I C T W O") == "PEŁNOMOCNICTWO"
    assert _despace("O D W O Ł A N I E") == "ODWOŁANIE"
    assert _despace("a b c") == "a b c"  # too short, left alone
    assert _despace("Jan Kowalski") == "Jan Kowalski"


@pytest.mark.parametrize("heading, expected", [
    ("P E Ł N O M O C N I C T W O", "pelnomocnictwo"),
    ("O D W O Ł A N I E", "odwolanie"),
])
def test_letter_spaced_heading_classifies(specs, heading, expected):
    scores = rule_scores(f"Warszawa, 1 marca 2026\n\n{heading}\n\nTreść pisma.", "dokument.pdf", specs)
    assert max(scores, key=scores.get) == expected
    assert scores[expected] >= 5


def test_filename_hint(specs):
    assert rule_scores("", "pelnomocnictwo_skan.pdf", specs)["pelnomocnictwo"] == 2.0
    assert set(rule_scores("", "dokument.pdf", specs).values()) == {0.0}
