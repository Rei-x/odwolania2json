"""o2j/doc_order.py: people lists in document order and under the principal that names them (offline, no LLM).

Texts are invented; the layout mirrors scanned powers of attorney: representation clause first
("reprezentowana przez: A, B"), signature block below with the same people in another order.
"""
from __future__ import annotations

import copy
import json

import pytest

from conftest import TRAIN
from o2j import doc_order as DO
from o2j import pdf as P


def _doc(*pages: str) -> P.Document:
    d = P.Document(path=None)
    d.pages = [P.Page(i + 1, t, "ocr", None) for i, t in enumerate(pages)]
    return d


def _pel(principals: list[tuple[str, list[str]]], attorneys: list[str] = ()) -> dict:
    return {"mocodawca": [{"data": {"imie_nazwisko": None, "krs": krs, "nazwa": name, "nip": None,
                                    "typ": "osoba_prawna"},
                           "podpisujacy": [{"imie_nazwisko": s} for s in signers]}
                          for (name, signers), krs in zip(principals, ("9990000001", "9990000002", "9990000003"))],
            "pelnomocnicy": [{"imie_nazwisko": a, "pesel": None} for a in attorneys]}


def _signers(r: dict) -> list[list[str]]:
    return [[p["imie_nazwisko"] for p in m["podpisujacy"]] for m in r["mocodawca"]]


ONE = """PEŁNOMOCNICTWO
Alfa Serwis spółka akcyjna z siedzibą w Opolu, KRS: 9990000001, reprezentowana przez: Halina Wrona – Prezes Zarządu,
Dorota Sowa – Członek Zarządu (dalej: „Mocodawca”), niniejszym udziela pełnomocnictwa: Krzysztof Dąb (radca prawny)
oraz Ewelina Grab (adwokat) do reprezentowania Mocodawcy.
Za Mocodawcę:
Dorota Sowa – Członek Zarządu
Halina Wrona – Prezes Zarządu
"""


def test_signers_follow_representation_clause_not_signature_layout(specs):
    r = _pel([("Alfa Serwis spółka akcyjna", ["Dorota Sowa", "Halina Wrona"])], ["Ewelina Grab", "Krzysztof Dąb"])
    changes = DO.apply(specs["pelnomocnictwo"], r, _doc(ONE))
    assert _signers(r) == [["Halina Wrona", "Dorota Sowa"]]
    assert [p["imie_nazwisko"] for p in r["pelnomocnicy"]] == ["Krzysztof Dąb", "Ewelina Grab"]
    assert {c["field"] for c in changes} == {"mocodawca[0].podpisujacy", "pelnomocnicy"}
    assert all(c["action"] == "order" for c in changes)


def test_order_already_right_is_a_noop(specs):
    r = _pel([("Alfa Serwis spółka akcyjna", ["Halina Wrona", "Dorota Sowa"])], ["Krzysztof Dąb", "Ewelina Grab"])
    before = copy.deepcopy(r)
    assert DO.apply(specs["pelnomocnictwo"], r, _doc(ONE)) == []
    assert r == before


def test_inflected_mentions_and_diacritics():
    text = ("Beta sp. z o.o., KRS 9990000001, reprezentowana przez Komplementariusza Hannę Krawczyk oraz "
            "Prezesa Roberta Sikorę, udziela pełnomocnictwa. Podpisy: Robert Sikora, Hanna Krawczyk")
    people = DO._People(DO.fold(text), ["Robert Sikora", "Hanna Krawczyk"])
    items = [{"imie_nazwisko": "Robert Sikora"}, {"imie_nazwisko": "Hanna Krawczyk"}]
    assert DO._ordered(items, people) == items[::-1]
    assert DO.fold("Łukasz Żółć") == "lukasz zolc"


def test_person_not_found_leaves_list_unchanged(specs):
    r = _pel([("Alfa Serwis spółka akcyjna", ["Dorota Sowa", "Zenon Nieobecny"])])
    before = copy.deepcopy(r)
    assert DO.apply(specs["pelnomocnictwo"], r, _doc(ONE)) == []
    assert r == before


def test_similar_names_are_told_apart():
    text = "reprezentowana przez: Janina Kowalska, Jan Kowalski. Podpisy: Jan Kowalski, Janina Kowalska"
    people = DO._People(DO.fold(text), ["Jan Kowalski", "Janina Kowalska"])
    assert people.spans("Jan Kowalski")[0][0] > people.spans("Janina Kowalska")[0][0]
    items = [{"imie_nazwisko": "Jan Kowalski"}, {"imie_nazwisko": "Janina Kowalska"}]
    assert DO._ordered(items, people) == items[::-1]


def test_company_as_attorney_is_never_reordered():
    assert DO._person_re("Kancelaria Prawna Nowak i Wspólnicy sp. k.") is None
    assert DO._person_re("Kowalski") is None


CONSORTIUM = """PEŁNOMOCNICTWO
Wykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum):
1) Gamma Systemy sp. k. z siedzibą w Katowicach, KRS: 9990000001, NIP: 999-111-22-33,
reprezentowana przez: Dorota Lis – Prezes Zarządu – Lider Konsorcjum,
2) Delta Budownictwo spółka z ograniczoną odpowiedzialnością z siedzibą w Opolu, KRS: 9990000002,
reprezentowana przez: Łukasz Sowiński – Prezes Zarządu – Partner Konsorcjum,
(dalej łącznie: „Mocodawca”), niniejszym udzielają pełnomocnictwa: 1. Dorota Kubik – radca prawny,
do reprezentowania Mocodawcy w sprawie dotyczącej środków ochrony prawnej.
Za Mocodawcę:
Łukasz Sowiński – Prezes Zarządu
Dorota Lis – Prezes Zarządu
"""


def test_joint_signature_block_signer_repeated_under_leader_is_dropped(specs):
    r = _pel([("Gamma Systemy sp. k.", ["Dorota Lis", "Łukasz Sowiński"]),
              ("Delta Budownictwo spółka z ograniczoną odpowiedzialnością", ["Łukasz Sowiński"])], ["Dorota Kubik"])
    changes = DO.apply(specs["pelnomocnictwo"], r, _doc(CONSORTIUM))
    assert _signers(r) == [["Dorota Lis"], ["Łukasz Sowiński"]]
    assert changes == [{"field": "mocodawca[0].podpisujacy", "action": "drop", "value": "Łukasz Sowiński",
                        "owner": "mocodawca[1]"}]


def test_person_named_for_both_principals_stays_under_both(specs):
    text = CONSORTIUM.replace("reprezentowana przez: Łukasz Sowiński", "reprezentowana przez: Dorota Lis")
    r = _pel([("Gamma Systemy sp. k.", ["Dorota Lis"]),
              ("Delta Budownictwo spółka z ograniczoną odpowiedzialnością", ["Dorota Lis"])])
    before = copy.deepcopy(r)
    assert DO.apply(specs["pelnomocnictwo"], r, _doc(text)) == []
    assert r == before


def test_signature_headings_attribute_people(specs):
    text = """Konsorcjum: 1) Omega Instalacje sp.j., KRS 9990000001; 2) Sigma Dachy sp. z o.o., KRS 9990000002
(dalej łącznie: „Mocodawca”), reprezentowani przez osoby podpisane poniżej, udzielają pełnomocnictwa: adw. Piotr Zając.
W imieniu Omega Instalacje sp.j.:
............................................
Agnieszka Kurek
Wspólnik
............................................
Robert Kurek
Wspólnik
W imieniu Sigma Dachy sp. z o.o.:
............................................
Marek Domański
Prezes Zarządu
"""
    r = _pel([("Omega Instalacje sp.j.", ["Agnieszka Kurek", "Robert Kurek"]),
              ("Sigma Dachy sp. z o.o.", ["Robert Kurek", "Marek Domański"])], ["Piotr Zając"])
    DO.apply(specs["pelnomocnictwo"], r, _doc(text))
    assert _signers(r) == [["Agnieszka Kurek", "Robert Kurek"], ["Marek Domański"]]


def test_no_owner_without_representation_cue(specs):
    # both principals before the grant, signers only in a joint block: the text does not say who signs for whom
    text = """Gamma Systemy sp. k., KRS: 9990000001 oraz Delta Budownictwo sp. z o.o., KRS: 9990000002 udzielają
pełnomocnictwa Dorocie Kubik do reprezentowania ich w sprawie. Podpisy: Dorota Lis, Łukasz Sowiński"""
    r = _pel([("Gamma Systemy sp. k.", ["Dorota Lis", "Łukasz Sowiński"]),
              ("Delta Budownictwo sp. z o.o.", ["Łukasz Sowiński"])])
    before = copy.deepcopy(r)
    assert DO.apply(specs["pelnomocnictwo"], r, _doc(text)) == []
    assert r == before


def test_single_principal_never_loses_signers(specs):
    r = _pel([("Alfa Serwis spółka akcyjna", ["Halina Wrona", "Dorota Sowa"])])
    DO.apply(specs["pelnomocnictwo"], r, _doc(ONE))
    assert _signers(r) == [["Halina Wrona", "Dorota Sowa"]]


def test_empty_or_unreadable_inputs(specs):
    assert DO.apply(specs["pelnomocnictwo"], {}, _doc("")) == []
    assert DO.apply(specs["pelnomocnictwo"], {"mocodawca": None, "pelnomocnicy": []}, _doc(ONE)) == []
    assert DO.apply(specs["odwolanie"], {"Odwolujacy": [], "Zamawiajacy": []}, _doc(ONE)) == []
    odd = {"mocodawca": ["x", {"data": None, "podpisujacy": [{"imie_nazwisko": None}]}], "pelnomocnicy": [None]}
    assert DO.apply(specs["pelnomocnictwo"], odd, _doc(ONE)) == []


def _train_pel():
    for case in sorted(p for p in TRAIN.iterdir() if (p / "pelnomocnictwo.json").exists()):
        yield case.name, json.loads((case / "pelnomocnictwo.json").read_text(encoding="utf-8")), \
            P.load(case / "pelnomocnictwo.pdf")


def test_training_ground_truth_is_already_in_document_order(specs):
    """The convention the rule encodes: applied to the organiser's reference JSON it changes nothing,
    and it restores reversed lists and signers copied to every principal."""
    spec, n_rev, n_copy = specs["pelnomocnictwo"], 0, 0
    for name, gt, doc in _train_pel():
        g = copy.deepcopy(gt)
        assert DO.apply(spec, g, doc) == [] and g == gt, name
        g, rev = copy.deepcopy(gt), False
        for lst in [m["podpisujacy"] for m in g["mocodawca"]] + [g["pelnomocnicy"]]:
            if len(lst) >= 2:
                lst.reverse()
                rev = True
        if rev:
            n_rev += 1
            DO.apply(spec, g, doc)
            assert g == gt, name
        if len(gt["mocodawca"]) >= 2:
            n_copy += 1
            g = copy.deepcopy(gt)
            everyone = [p for m in g["mocodawca"] for p in m["podpisujacy"]]
            for m in g["mocodawca"]:
                m["podpisujacy"] = copy.deepcopy(everyone)
            DO.apply(spec, g, doc)
            assert g == gt, name
    assert n_rev >= 40 and n_copy >= 5


def test_pipeline_applies_doc_order_and_traces_it(monkeypatch):
    """End to end with a stub model that copies the signature-block order and repeats a partner's signer."""
    from o2j.config import load_settings
    from o2j.pipeline import Pipeline

    s = load_settings()
    s["llm"] = {"base_url": "http://127.0.0.1:9/v1", "api_key": "none", "model": "stub-model", "retries": 0}
    s["ocr"] = {**s.get("ocr", {}), "engine": "none", "preprocess": None}
    s.setdefault("extraction", {})["mode"] = "llm"
    s["router"] = {"enabled": False}
    s["verify"] = {"max_rounds": 0}
    s["postprocess"] = {"snap_to_text": False, "rules_fill": False}
    p = Pipeline(s)
    model_out = _pel([("Gamma Systemy sp. k.", ["Dorota Lis", "Łukasz Sowiński"]),
                      ("Delta Budownictwo spółka z ograniczoną odpowiedzialnością", ["Łukasz Sowiński"])],
                     ["Dorota Kubik"])

    class Stub:
        model = "stub-model"

        def extract_json(self, system, user, schema, name="extraction", images=None, model=None, temperature=None):
            out = {"typ": "pelnomocnictwo"} if name == "classification" else copy.deepcopy(model_out)
            return out, {"model": self.model, "usage": {}, "raw": "{}", "attempts": 1}
    p.llm = Stub()
    monkeypatch.setattr(P, "load", lambda *a, **k: _doc(CONSORTIUM))
    doctype, result, trace = p.process(TRAIN / "przyklad_01" / "pelnomocnictwo.pdf")
    assert doctype == "pelnomocnictwo"
    assert _signers(result) == [["Dorota Lis"], ["Łukasz Sowiński"]]
    assert trace["doc_order"][0]["action"] == "drop"
    assert not any(e["field"] == "mocodawca[0].podpisujacy[1].imie_nazwisko" for e in trace["evidence"])


@pytest.mark.parametrize("key, bad", [("order", "alphabetical"), ("owner", "first")])
def test_wizard_rejects_unknown_list_options(key, bad):
    from o2j import wizard as W
    yaml_ok = ("name: lista_osob\ndescription: x\nfields:\n  osoby:\n    type: array\n    {opt}\n"
               "    items: {{type: object, properties: {{imie_nazwisko: {{type: string, description: x}}}}}}\n")
    assert W.validate(yaml_ok.format(opt="order: document\n    owner: mention"))["ok"]
    v = W.validate(yaml_ok.format(opt=f"{key}: {bad}"))
    assert not v["ok"] and [e["path"] for e in v["errors"]] == ["fields.osoby"] and key in v["errors"][0]["msg"]
