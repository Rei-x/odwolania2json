from pathlib import Path

import pytest

from o2j import extract as E
from o2j import pdf as P


# ------------------------------------------------------------------ postprocess
def test_postprocess_full_odwolanie(specs):
    raw = {
        "OdwolanieKIO": {"czynnosc_powod_id": "9", "data": "16 czerwca 2026", "miejscowosc": " Koszalin,",
                         "czynnosc_opis": "something the model made up"},
        "Odwolujacy": [None, {}, {"nazwa": "X", "krs": "405188", "nip": "999-928-40-65",
                                  "pelnomocnik": {"imie_nazwisko": "adw. JAN KOWALSKI"}}],
        "Zamawiajacy": {"nazwa": "Y"},  # scalar instead of list -> wrapped
        "ZamowieniePubliczne": {"numer_bzp": "2026/BZP 999778", "numer_ted": "2026/S 055-999137"},
        "unexpected_key": 1,
    }
    out = E.postprocess(specs["odwolanie"], raw)
    assert list(out) == list(specs["odwolanie"].fields)
    k = out["OdwolanieKIO"]
    assert k["data"] == "2026-06-16"
    assert k["miejscowosc"] == "Koszalin"
    assert k["czynnosc_powod_id"] == 9
    assert k["czynnosc_opis"] == "Decyzja o unieważnieniu postępowania"  # derived, overrides model output
    assert len(out["Odwolujacy"]) == 1  # None and {} filtered out
    o = out["Odwolujacy"][0]
    assert o["krs"] == "0000405188" and o["nip"] == "9999284065"
    assert o["pelnomocnik"] == {"imie_nazwisko": "Jan Kowalski", "nazwa": None, "mail": None}
    assert out["Zamawiajacy"] == [{"krs": None, "nazwa": "Y", "nip": None, "regon": None,
                                   "prowadzacy_postepowanie": None}]
    assert out["ZamowieniePubliczne"]["numer_bzp"] == "2026/BZP00999778"
    assert out["ZamowieniePubliczne"]["numer_ted"] == "999137-2026"
    assert "unexpected_key" not in out


@pytest.mark.parametrize("raw, expected_id", [
    (9, 9), ("9", 9), (" 4 ", 4),
    ("Decyzja o odrzuceniu oferty", 1),
    ("decyzja o odrzuceniu oferty", 1),
    (99, None), ("coś innego", None), (None, None),
])
def test_enum_coercion_and_derived_label(specs, raw, expected_id):
    out = E.postprocess(specs["odwolanie"], {"OdwolanieKIO": {"czynnosc_powod_id": raw}})["OdwolanieKIO"]
    assert out["czynnosc_powod_id"] == expected_id
    labels = {e["value"]: e["label"] for e in specs["odwolanie"].fields["OdwolanieKIO"]["properties"]
              ["czynnosc_powod_id"]["values"]}
    assert out["czynnosc_opis"] == labels.get(expected_id)


def test_plain_string_enum(specs):
    out = E.postprocess(specs["pelnomocnictwo"], {"mocodawca": [{"data": {"typ": "osoba_fizyczna", "nazwa": "A"}}]})
    assert out["mocodawca"][0]["data"]["typ"] == "osoba_fizyczna"
    out = E.postprocess(specs["pelnomocnictwo"], {"mocodawca": [{"data": {"typ": "spółka", "nazwa": "A"}}]})
    assert out["mocodawca"][0]["data"]["typ"] is None


def test_person_dedupe_and_null_filtering(specs):
    raw = {
        "mocodawca": [{
            "data": {"typ": "osoba_prawna", "nazwa": "Belmoria S.A."},
            "podpisujacy": [{"imie_nazwisko": "Paweł Wierzowiecki"},
                            {"imie_nazwisko": "Paweł Stanisław Wierzowiecki"},  # e-signature stamp variant
                            {"imie_nazwisko": None},
                            {"imie_nazwisko": "Oliwia Kaczmarek"}],
        }, {"data": None, "podpisujacy": []}],  # all-null mocodawca dropped
        "pelnomocnicy": [{"imie_nazwisko": "r.pr. Anna Nowak", "pesel": "85010112345"},
                         {"imie_nazwisko": "ANNA NOWAK", "pesel": None},
                         {"imie_nazwisko": "Jan Kowalski", "pesel": None}],
    }
    out = E.postprocess(specs["pelnomocnictwo"], raw)
    assert len(out["mocodawca"]) == 1
    assert [p["imie_nazwisko"] for p in out["mocodawca"][0]["podpisujacy"]] == ["Paweł Wierzowiecki", "Oliwia Kaczmarek"]
    assert out["pelnomocnicy"] == [{"imie_nazwisko": "Anna Nowak", "pesel": 85010112345},
                                   {"imie_nazwisko": "Jan Kowalski", "pesel": None}]


def test_postprocess_none_gives_skeleton(specs):
    for spec in specs.values():
        assert E.postprocess(spec, None) == spec.skeleton()


def test_przelew_amount_and_accounts(specs):
    out = E.postprocess(specs["przelew"], {"przelew_bankowy": {
        "kwota": "-15 000,00 PLN", "data_operacji": "21.03.2026",
        "z_rachunku": "PL05 4706 8028 7581 5397 2145 5024", "tytul": "  opłata   skarbowa "}})["przelew_bankowy"]
    assert out["kwota"] == 15000.0
    assert out["data_operacji"] == "2026-03-21"
    assert out["z_rachunku"] == "05470680287581539721455024"
    assert out["tytul"] == "opłata skarbowa"


def test_derived_fields_and_fill_ratio(specs):
    assert E.derived_fields(specs["odwolanie"]) == {"czynnosc_opis"}
    assert E.fill_ratio(specs["odwolanie"].skeleton()) == 0.0
    assert E.fill_ratio({"a": 1, "b": None}) == 0.5


def test_build_prompt_contains_guide_and_examples(specs):
    system, user = E.build_prompt(specs["przelew"], "DOC TEXT", [("EX TEXT", '{"a": 1}')])
    assert "przelew" in system and "kwota" in system
    assert "PRZYKŁAD 1" in user and "EX TEXT" in user and user.rstrip().endswith("dokumentu do analizy.")


# ------------------------------------------------------------------ grounding
@pytest.fixture
def doc():
    return P.Document(path=Path("synthetic.pdf"), pages=[
        P.Page(1, "Koszalin, 16 czerwca 2026 roku\nOdwołujący: Belmoria S.A.,\nKRS 0000 405 188, NIP 999-928-40-65", "text"),
        P.Page(2, "Ogłoszenie TED 2026/S 055-999137 z dnia 20.03.2026\n"
                  "Rachunek PL 68 4382 2304 9992 2952 6283 4736 kwota 15 000,00 zł\nPostępowanie z 5 V 2026", "text"),
    ])


def _by_field(ev):
    return {e["field"]: e for e in ev}


def test_ground_locates_values(doc):
    res = {"a": {"data": "2026-06-16", "krs": "0000405188", "nip": "9999284065", "miasto": "Koszalin",
                 "opis": "Decyzja", "brak": None},
           "ted": "999137-2026", "dzien": "2026-03-20", "rzym": "2026-05-05",
           "rachunek": "68438223049992295262834736", "kwota": 15000.0,
           "nope": "Zupełnie inny tekst który nie występuje"}
    ev = _by_field(E.ground(doc, res, {"opis"}))
    assert "a.brak" not in ev  # nulls are not grounded
    assert ev["a.data"]["method"] == "located" and ev["a.data"]["page"] == 1
    assert ev["a.data"]["quote"] == "16 czerwca 2026"  # date written in words
    assert ev["a.krs"]["quote"] == "0000 405 188"  # digit-level match ignores spaces
    assert ev["a.nip"]["quote"] == "999-928-40-65"  # ... and dashes
    assert ev["a.miasto"]["page"] == 1
    assert ev["a.opis"]["method"] == "derived"
    assert ev["ted"]["page"] == 2 and "999137" in ev["ted"]["quote"]  # TED NNNNNN-YYYY found as YYYY/S ###-NNNNNN
    assert ev["dzien"]["quote"] == "20.03.2026"
    assert ev["rzym"]["page"] == 2 and ev["rzym"]["quote"] == "5 V 2026"
    assert ev["rachunek"]["quote"] == "68 4382 2304 9992 2952 6283 4736"
    assert ev["kwota"]["page"] == 2 and ev["kwota"]["quote"].startswith("15 000,00")
    assert ev["nope"]["method"] == "inferred"
    for e in ev.values():
        if e["method"] == "located":
            assert e["score"] >= 80 and e["quote"] in e["context"]


def test_ground_list_paths(doc):
    ev = E.ground(doc, {"Odwolujacy": [{"krs": "0000405188"}]})
    assert ev[0]["field"] == "Odwolujacy[0].krs" and ev[0]["method"] == "located"
