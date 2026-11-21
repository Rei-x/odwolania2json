"""Doctype inference from an example document (o2j.wizard.infer): deterministic post-processing, LLM mocked.

Asserted:
- names are sanitised to NAME_RE (diacritics folded, snake_case, no leading digit) and never collide with
  built-in / existing types;
- keywords survive only when they really occur in the example text; values (digits) and generic domain words
  are dropped; upper-case line-start phrases become case-sensitive heading regexes with weight 5;
- keywords that also fire on reference documents of built-in types are dropped with a warning;
- field proposals map to allowed types / normalisers (aliases, unknown -> string, enum without values -> string,
  normaliser forces the output type), flat paths with [] build nested objects / arrays of objects;
- infer() with a mocked LLM returns YAML that validates and loads, and the new type wins on its example.
"""
import re

from o2j import wizard as W
from o2j.classify import rule_scores

EXAMPLE = """=== Strona 1 ===
Gdańsk, 14 października 2025 r.
Krajowa Izba Odwoławcza
Sygn. akt KIO 3812/25
PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO
po stronie zamawiającego
Przystępujący: HYDRO-TRANS S.A., NIP 5842735212, KRS 0000123456
Działając w imieniu wykonawcy zgłaszam przystąpienie do postępowania odwoławczego.
Pełnomocnik: Jan Kowalski, jan.kowalski@example.com
"""


class FakeLLM:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    def extract_json(self, system, user, schema, name="extraction", images=None, model=None, temperature=None, timeout=None):
        self.calls.append({"schema": schema, "model": model, "temperature": temperature, "user": user})
        return self.proposal, {"model": model or "fake", "usage": {}, "attempts": 1}


PROPOSAL = {
    "name": "Przystąpienie",
    "title": "PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO",
    "description": "Pismo wykonawcy zgłaszające przystąpienie do postępowania odwoławczego przed KIO.",
    "not_this": "odwołanie ani wyrok KIO",
    "keywords": [
        {"phrase": "PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO", "weight": 5},
        {"phrase": "zgłaszam przystąpienie", "weight": 3},
        {"phrase": "HYDRO-TRANS S.A.", "weight": 2},  # a value (company), but no digits: kept only if in text
        {"phrase": "KIO 3812/25", "weight": 3},  # digits -> dropped
        {"phrase": "faktura korygująca", "weight": 3},  # not in the text -> dropped
        {"phrase": "po stronie zamawiającego", "weight": 1},  # generic domain words only -> dropped
    ],
    "instructions": ["Sygnaturę przepisz razem z przedrostkiem, np. 'KIO 1234/25'.",
                     "Daty podawaj w formacie polskim."],  # contradicts the ISO default -> dropped
    "fields": [
        {"path": "Przystapienie.data", "type": "date", "description": "Data pisma.", "normalize": "date",
         "values": [], "example": "2025-10-14"},
        {"path": "Przystapienie.miejscowość", "type": "string", "description": "Miejscowość z nagłówka.",
         "normalize": "none", "values": [], "example": "Gdańsk"},
        {"path": "Przystapienie.strona", "type": "enum", "description": "Strona przystąpienia.", "normalize": "none",
         "values": ["zamawiajacy", "odwolujacy"], "example": "zamawiajacy"},
        {"path": "Przystepujacy[].nazwa", "type": "string", "description": "Nazwa wykonawcy.", "normalize": "strip",
         "values": [], "example": "HYDRO-TRANS S.A."},
        {"path": "Przystepujacy[].nip", "type": "string", "description": "NIP.", "normalize": "nip",
         "values": [], "example": "5842735212"},
        {"path": "Pelnomocnicy[].imie_nazwisko", "type": "string", "description": "Pełnomocnik.",
         "normalize": "person", "values": [], "example": "Jan Kowalski"},
    ],
}


# ---------------------------------------------------------------- names
def test_sanitize_name():
    assert W.sanitize_name("Przystąpienie do postępowania") == "przystapienie_do_postepowania"
    assert W.sanitize_name("Odpowiedź na odwołanie!") == "odpowiedz_na_odwolanie"
    assert W.sanitize_name("123 faktura") == "faktura"
    assert W.sanitize_name("przystapienie_do_postepowania_odwolawczego") == "przystapienie"
    assert W.sanitize_name("", "Faktura VAT korygująca") == "faktura_vat_korygujaca"
    assert W.sanitize_name("", "") == "nowy_typ"
    assert W.sanitize_name("odwolanie") == "odwolanie_2"  # built-in
    assert W.sanitize_name("faktura", taken={"faktura", "faktura_2"}) == "faktura_3"
    long = W.sanitize_name("a" * 80)
    assert W.NAME_RE.match(long) and len(long) <= 41


def test_sanitize_key():
    assert W.sanitize_key("miejscowość") == "miejscowosc"
    assert W.sanitize_key("Zamówienie Publiczne") == "Zamowienie_Publiczne"
    assert W.sanitize_key("1_strona") == "f_1_strona"
    assert W.sanitize_key("  ") == ""


# ---------------------------------------------------------------- keywords
def test_keyword_pattern_requires_occurrence():
    pat, heading = W.keyword_pattern("PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO", EXAMPLE)
    assert heading and pat.startswith(r"^\s*(?-i:")
    assert re.search(pat, EXAMPLE, flags=re.M | re.I)
    # case-sensitive heading: a letter that merely mentions the document in running text does not match
    assert not re.search(pat, "w piśmie przystąpienie do postępowania odwoławczego zgłoszono", flags=re.M | re.I)
    pat2, heading2 = W.keyword_pattern("zgłaszam  przystąpienie", EXAMPLE)
    assert not heading2 and re.search(pat2, EXAMPLE, flags=re.I)
    assert W.keyword_pattern("faktura korygująca", EXAMPLE) is None
    assert W.keyword_pattern("KIO 3812/25", EXAMPLE) is None
    assert W.keyword_pattern("po stronie zamawiającego", EXAMPLE) is None
    assert W.keyword_pattern("abc", EXAMPLE) is None


def test_long_sentences_and_variants_are_not_keywords():
    assert W.keyword_pattern("Działając w imieniu wykonawcy zgłaszam przystąpienie do postępowania", EXAMPLE) is None
    kw, _ = W.infer_keywords([{"phrase": "zgłaszam przystąpienie", "weight": 3},
                              {"phrase": "wykonawcy zgłaszam przystąpienie", "weight": 2}], [EXAMPLE])
    assert len(kw) == 1


def test_letter_spaced_heading_is_found():
    text = "P R Z Y S T Ą P I E N I E\ntreść"
    got = W.keyword_pattern("PRZYSTĄPIENIE", text)
    assert got is not None and got[1]


def test_infer_keywords_filters_and_weights():
    kw, warns = W.infer_keywords(PROPOSAL["keywords"], [EXAMPLE], PROPOSAL["title"])
    pats = list(kw)
    assert any("(?-i:PRZYSTĄPIENIE" in p for p in pats)
    assert all(kw[p] == 5 for p in pats if p.startswith(r"^\s*(?-i:"))
    assert all(1 <= w <= 5 for w in kw.values())
    assert not any("3812" in p or "faktura" in p for p in pats)
    assert not warns


def test_infer_keywords_must_occur_in_every_example():
    other = "=== Strona 1 ===\nPRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO\ntreść bez formuły"
    kw, _ = W.infer_keywords([{"phrase": "zgłaszam przystąpienie", "weight": 3}], [EXAMPLE, other])
    assert kw == {}


def test_infer_keywords_drop_those_firing_on_builtin_references():
    ref = ["ODWOŁANIE\nOdwołujący zgłaszam przystąpienie ... "]
    kw, warns = W.infer_keywords([{"phrase": "zgłaszam przystąpienie", "weight": 3},
                                  {"phrase": "PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO", "weight": 5}],
                                 [EXAMPLE], reference=ref)
    assert len(kw) == 1 and next(iter(kw)).startswith(r"^\s*(?-i:")
    assert warns and "zgłaszam przystąpienie" in warns[0]


# ---------------------------------------------------------------- fields
def test_leaf_type_and_normaliser_mapping():
    assert W.leaf_from_proposal("kwota", {"type": "amount", "normalize": "amount"})["type"] == "number"
    assert W.leaf_from_proposal("x", {"type": "weird", "normalize": "none"}) == {"type": "string"}
    assert W.leaf_from_proposal("x", {"type": "enum", "values": ["tak"]})["type"] == "string"
    e = W.leaf_from_proposal("x", {"type": "enum", "values": ["a", "b", "a"], "description": "d"})
    assert e == {"type": "enum", "values": ["a", "b"], "description": "d"}
    assert W.leaf_from_proposal("x", {"type": "boolean"})["values"] == ["tak", "nie"]
    # normaliser decides the output type
    assert W.leaf_from_proposal("termin", {"type": "string", "normalize": "date"})["type"] == "date"
    # unknown normaliser -> field-name heuristic
    nip = W.leaf_from_proposal("nip", {"type": "string", "normalize": "bogus"})
    assert nip["normalize"] == ["nip"] and nip["pattern"]
    # explicit normaliser keeps the heuristic's validator when they agree
    krs = W.leaf_from_proposal("krs", {"type": "string", "normalize": "krs"})
    assert krs["normalize"] == ["krs"] and krs["pattern"] == r"\d{10}"
    person = W.leaf_from_proposal("pelnomocnik", {"type": "string", "normalize": "person"})
    assert person["single_person"] is True
    lst = W.leaf_from_proposal("zarzuty", {"type": "array_string", "description": "Zarzuty."})
    assert lst == {"type": "array", "description": "Zarzuty.", "items": {"type": "string"}}
    assert all(n in W.NORMALIZERS for n in W.leaf_from_proposal("data", {"type": "date"}).get("normalize", []))


def test_fields_from_flat_paths():
    fields, warns = W.fields_from_proposal(PROPOSAL["fields"])
    assert list(fields) == ["Przystapienie", "Przystepujacy", "Pelnomocnicy"]
    assert fields["Przystapienie"]["type"] == "object"
    assert list(fields["Przystapienie"]["properties"]) == ["data", "miejscowosc", "strona"]
    assert fields["Przystepujacy"]["type"] == "array"
    assert fields["Przystepujacy"]["items"]["properties"]["nip"]["normalize"] == ["nip"]
    assert fields["Pelnomocnicy"]["dedupe"] == "person"
    assert not warns


def test_fields_duplicates_conflicts_and_limit():
    items = [{"path": "a", "type": "string"}, {"path": "a", "type": "date"}, {"path": "a.b", "type": "string"},
             {"path": "..", "type": "string"}, {"path": "g.x", "type": "string"}]
    fields, _ = W.fields_from_proposal(items)
    assert fields["a"] == {"type": "string"} and fields["g"]["properties"]["x"] == {"type": "string"}
    many = [{"path": f"pole_{i}", "type": "string"} for i in range(50)]
    fields, warns = W.fields_from_proposal(many, limit=10)
    assert len(fields) == 10 and warns


# ---------------------------------------------------------------- end to end with a mocked LLM
def test_infer_end_to_end_mocked(tmp_path):
    from o2j.config import load_settings
    from o2j.spec import load_specs
    specs = load_specs(load_settings()["paths"]["doctypes"])
    llm = FakeLLM(PROPOSAL)
    res = W.infer([EXAMPLE], llm, model="small-8b", taken={"przystapienie"}, specs=specs, reference=[])
    call = llm.calls[0]
    assert call["model"] == "small-8b" and call["temperature"] == 0
    assert call["schema"]["additionalProperties"] is False and "PRZYSTĄPIENIE" in call["user"]
    assert res["validation"]["ok"], res["validation"]["errors"]
    spec = res["spec"]
    assert spec["name"] == "przystapienie_2"  # existing name taken
    assert "Nie jest nim" in spec["description"]
    assert spec["description"].startswith("Przystąpienie do postępowania odwoławczego.")
    assert "KIO 1234/25" in spec["instructions"] and "polskim" not in spec["instructions"]
    loaded = W.load_spec_text(res["yaml"])
    assert set(loaded.skeleton()) == {"Przystapienie", "Przystepujacy", "Pelnomocnicy"}
    allspecs = {**specs, spec["name"]: loaded}
    sc = rule_scores(EXAMPLE, "", allspecs)
    assert max(sc, key=sc.get) == spec["name"]
    assert not any("nie wskazują" in w for w in res["warnings"])


def test_infer_rejects_empty_text():
    import pytest
    with pytest.raises(ValueError):
        W.infer(["   "], FakeLLM(PROPOSAL))
    with pytest.raises(ValueError):
        W.infer([EXAMPLE], FakeLLM({**PROPOSAL, "fields": []}))


def test_reference_texts_from_train(tmp_path):
    from o2j.config import load_settings
    ref = W.reference_texts(load_settings()["paths"].get("train"), per_type=1)
    assert ref and {t for t, _ in ref} <= W.BUILTIN
    # the example keywords do not fire on built-in reference documents
    kw, _ = W.infer_keywords(PROPOSAL["keywords"], [EXAMPLE], PROPOSAL["title"])
    assert not any(re.search(p, t, flags=re.M | re.I) for p in kw for _, t in ref if p.startswith(r"^\s*(?-i:"))
