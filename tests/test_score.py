"""eval/score.py: organiser rules.

TP: present in both and equal (fuzzy >= 80% only for FUZZY_FIELDS); TN: absent in both;
FP: only in prediction, or present in both but different; FN: only in ground truth.
Lists are paired by content, not by position.
"""
import json

import pytest

from eval.score import FUZZY_FIELDS, compare, f1, leaf_equal, score_dirs


def kinds(pred, gt):
    out = []
    compare(pred, gt, "", out)
    return {path: kind for kind, path, _, _ in out}


@pytest.mark.parametrize("pred, gt, expected", [
    ("a", "a", "TP"),
    (None, None, "TN"),
    ("", None, "TN"),
    ("a", None, "FP"),
    ("a", "b", "FP"),
    (None, "a", "FN"),
    ("  ", "a", "FN"),
    (15000, "15000.00", "TP"),
    (200.0, 200, "TP"),
    (1, "1", "TP"),
])
def test_leaf_semantics(pred, gt, expected):
    assert kinds({"x": pred}, {"x": gt}) == {"x": expected}


def test_fuzzy_only_for_listed_fields():
    gt_name = "Kancelaria Adwokacka Spółka z ograniczoną odpowiedzialnością"
    near = "Kancelaria Adwokacka Sp. z ograniczoną odpowiedzialnością"
    assert leaf_equal(near, gt_name, "Odwolujacy[0].pelnomocnik.nazwa")
    assert leaf_equal("Jan Kowalsky", "Jan Kowalski", "Odwolujacy[0].nazwa")
    # same similarity on a non-fuzzy field must be exact
    assert not leaf_equal("Jan Kowalsky", "Jan Kowalski", "Odwolujacy[0].pelnomocnik.imie_nazwisko")
    assert not leaf_equal("Jan Kowalsky", "Jan Kowalski", "mocodawca[0].podpisujacy[0].imie_nazwisko")
    # below threshold on a fuzzy field
    assert not leaf_equal("Zupełnie coś innego", "Dostawa sprzętu komputerowego", "ZamowieniePubliczne.tytul")


def test_fuzzy_field_list():
    assert FUZZY_FIELDS == {"Odwolujacy[].pelnomocnik.nazwa", "przelew_bankowy.tytul", "Odwolujacy[].nazwa",
                            "Zamawiajacy[].nazwa", "ZamowieniePubliczne.tytul"}


def test_whitespace_is_normalised():
    assert leaf_equal("Jan  Kowalski\n", "Jan Kowalski", "x")


def test_lists_matched_by_content_not_position():
    gt = {"pelnomocnicy": [{"imie_nazwisko": "Anna Nowak", "pesel": None},
                           {"imie_nazwisko": "Jan Kowalski", "pesel": 85010112345}]}
    pred = {"pelnomocnicy": list(reversed(gt["pelnomocnicy"]))}
    k = kinds(pred, gt)
    assert sorted(k.values()) == ["TN", "TP", "TP", "TP"]


def test_list_extra_and_missing_items():
    gt = {"p": [{"n": "A"}, {"n": "B"}]}
    assert sorted(kinds({"p": [{"n": "A"}]}, gt).values()) == ["FN", "TP"]
    assert sorted(kinds({"p": [{"n": "A"}, {"n": "B"}, {"n": "C"}]}, gt).values()) == ["FP", "TP", "TP"]
    assert sorted(kinds({"p": []}, gt).values()) == ["FN", "FN"]


def test_nested_null_object_vs_values():
    gt = {"o": {"a": "1", "b": None}}
    assert kinds({"o": None}, gt) == {"o.a": "FN", "o.b": "TN"}
    assert kinds({}, {}) == {}


def test_f1():
    assert f1({"TP": 0, "FP": 0, "FN": 0}) == 1.0
    assert f1({"TP": 2, "FP": 1, "FN": 1}) == pytest.approx(4 / 6)


@pytest.mark.xfail(reason="BUG eval/score.py _norm(): digit strings are compared as floats, so identifiers "
                          "differing only in leading zeros (KRS '405188' vs '0000405188') count as TP; "
                          "the organiser rule is exact match for non-fuzzy fields")
def test_identifier_leading_zeros_are_not_equal():
    assert kinds({"krs": "405188"}, {"krs": "0000405188"}) == {"krs": "FP"}


def test_score_dirs(tmp_path):
    gt, pred = tmp_path / "gt", tmp_path / "pred"
    (gt / "c1").mkdir(parents=True)
    (pred / "c1").mkdir(parents=True)
    (gt / "c1" / "przelew.json").write_text(json.dumps({"przelew_bankowy": {"kwota": 200.0, "tytul": "abc", "x": None}}))
    (pred / "c1" / "przelew.json").write_text(json.dumps({"przelew_bankowy": {"kwota": "200,00", "tytul": "xyz", "x": None}}))
    (gt / "c1" / "missing.json").write_text(json.dumps({"a": "v"}))  # no prediction file -> FN
    (gt / "c1" / "negative.json").write_text("{}")
    (pred / "c1" / "negative.json").write_text("{}")
    r = score_dirs(pred, gt)
    assert r["counts"] == {"TP": 1, "FP": 1, "TN": 1, "FN": 1}
    assert r["f1"] == pytest.approx(0.5)
    assert r["per_field"]["przelew:przelew_bankowy.kwota"]["TP"] == 1
