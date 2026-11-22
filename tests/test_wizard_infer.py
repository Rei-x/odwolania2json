"""Doctype inference from an example document (o2j.wizard.infer): deterministic post-processing, LLM mocked.

Asserted:
- names are sanitised to NAME_RE (diacritics folded, snake_case, no leading digit) and never collide with
  built-in / existing types;
- keywords survive only when they really occur in the example text; values (digits) and generic domain words
  are dropped; patterns are case-insensitive, whitespace/hyphen-tolerant and never line-anchored; the title
  weighs 5, at most 3 domain phrases weigh 1-3; one-word stamps/labels ("ZATWIERDZAM") are no keywords;
- domain keywords that also fire on reference documents of built-in types are dropped with a warning; the title
  is kept there only while the built-in type still wins those documents confidently;
- a type inferred from ONE "Informacja z otwarcia ofert" (capitalised heading, Legnica-like layout) also wins on
  another issuer's document of that kind (mixed-case title, other layout) and never on built-in documents;
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
    pat = W.keyword_pattern("PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO", EXAMPLE, title=True)
    assert pat and not pat.startswith("^") and "(?-i:" not in pat
    assert re.search(pat, EXAMPLE, flags=re.M | re.I)
    pat2 = W.keyword_pattern("zgłaszam  przystąpienie", EXAMPLE)
    assert pat2 and re.search(pat2, EXAMPLE, flags=re.I)
    assert W.keyword_pattern("faktura korygująca", EXAMPLE) is None
    assert W.keyword_pattern("KIO 3812/25", EXAMPLE) is None
    assert W.keyword_pattern("po stronie zamawiającego", EXAMPLE) is None
    assert W.keyword_pattern("abc", EXAMPLE) is None


def test_keyword_pattern_tolerates_case_layout_and_hyphens():
    pat = W.keyword_pattern("INFORMACJA Z OTWARCIA OFERT", "Legnica\nINFORMACJA Z OTWARCIA OFERT\nWybór", title=True)
    for other in ("Numer postępowania: ZGO/ZP/18/2021\nInformacja z otwarcia ofert\nDziałając",  # mixed case
                  "ski 15:37:59 +02'00' Informacja z otwarcia ofert Dotyczy postępowania",  # inside a longer line
                  "ZP 36/25 Informacja z otwarcia\nofert z dnia 27.02.2026 r",  # line break inside the phrase
                  "I N F O R M A C J A  Z  O T W A R C I A  O F E R T"):  # letter-spaced heading
        assert re.search(pat, rule_text(other), flags=re.M | re.I), other
    nr = W.keyword_pattern("Nr oferty", "Nr oferty Firma")
    assert all(re.search(nr, t, flags=re.I) for t in ("Nr\noferty", "NR OFERTY", "nr-oferty", "Nr. oferty"))
    firma = W.keyword_pattern("Nazwa (firma) i adres Wykonawcy", "Nr Nazwa (firma) i adres Wykonawcy Wartość")
    assert firma and re.search(firma, "NAZWA FIRMA I ADRES WYKONAWCY", flags=re.I)
    assert not re.search(nr, "nr 5 oferty", flags=re.I)  # tolerant to separators, not to other words


def test_paraphrased_title_is_replaced_by_the_documents_wording():
    other = OTWARCIE_OTHER
    assert W.title_in_text("Informacja o otwarciu ofert", other) == "Informacja z otwarcia ofert"
    assert W.title_in_text("Protokół z otwarcia ofert", other) is None  # a word of the title is missing
    assert W.title_in_text("Informacja", "Zamawiający informuje") is None  # one stem is too weak
    kw, _ = W.infer_keywords([], [other], "Informacja o otwarciu ofert")
    assert list(kw.values()) == [5] and re.search(next(iter(kw)), "INFORMACJA Z OTWARCIA OFERT", flags=re.I)


def rule_text(t: str) -> str:
    from o2j.classify import _despace
    return _despace(t)


def test_single_word_stamps_and_labels_are_not_keywords():
    text = "INFORMACJA Z OTWARCIA OFERT\ntabela\nZATWIERDZAM\nOpracowała:\nMocodawca udziela pełnomocnictwa"
    assert W.keyword_pattern("ZATWIERDZAM", text) is None  # stands alone on a line: approval stamp of one issuer
    assert W.keyword_pattern("Opracowała", text) is None
    assert W.keyword_pattern("Mocodawca", text)  # a long word inside running text is still a keyword
    assert W.keyword_pattern("tabela", text) is None  # short single word
    assert W.keyword_pattern("PEŁNOMOCNICTWO", "PEŁNOMOCNICTWO\ntreść", title=True)  # the title may be one word


def test_long_sentences_and_variants_are_not_keywords():
    assert W.keyword_pattern("Działając w imieniu wykonawcy zgłaszam przystąpienie do postępowania", EXAMPLE) is None
    kw, _ = W.infer_keywords([{"phrase": "zgłaszam przystąpienie", "weight": 3},
                              {"phrase": "wykonawcy zgłaszam przystąpienie", "weight": 2}], [EXAMPLE])
    assert len(kw) == 1


def test_letter_spaced_heading_is_found():
    text = "P R Z Y S T Ą P I E N I E\ntreść"
    assert W.keyword_pattern("PRZYSTĄPIENIE", text, title=True)


def test_infer_keywords_filters_and_weights():
    kw, warns = W.infer_keywords(PROPOSAL["keywords"], [EXAMPLE], PROPOSAL["title"])
    pats = list(kw)
    assert kw[pats[0]] == 5 and re.search(pats[0], "przystąpienie do postępowania odwoławczego", flags=re.I)
    assert not any(p.startswith("^") or "(?-i:" in p for p in pats)
    assert all(1 <= w <= 3 for w in list(kw.values())[1:])
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
    assert list(kw.values()) == [5] and "przyst" in next(iter(kw))
    assert warns and "zgłaszam przystąpienie" in warns[0]


def test_title_firing_on_a_reference_is_kept_only_while_the_builtin_still_wins():
    ref = ["ODWOŁANIE\nZamawiający przekazał PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO wykonawcy ..."]
    props = [{"phrase": "zgłaszam przystąpienie", "weight": 3}]
    title = PROPOSAL["title"]
    kw, _ = W.infer_keywords(props, [EXAMPLE], title, ref, reference_scores=[12.0])  # odwołanie wins 12 : 5
    assert 5 in kw.values()
    kw, warns = W.infer_keywords(props, [EXAMPLE], title, ref, reference_scores=[6.0])  # 6 : 5 would not be sure
    assert 5 not in kw.values() and warns
    kw, _ = W.infer_keywords(props, [EXAMPLE], title, ref)  # no scores known: strict
    assert 5 not in kw.values()


def test_domain_phrases_are_limited_and_topic_related_first():
    text = ("INFORMACJA Z OTWARCIA OFERT\nWybór Wykonawcy zadania pn. budowa\nkoszty dojazdu ekipy\n"
            "Nr oferty Cena oferty brutto\nfirmy złożyły oferty w terminie")
    props = [{"phrase": "koszty dojazdu ekipy", "weight": 3}, {"phrase": "Wybór Wykonawcy zadania pn.", "weight": 3},
             {"phrase": "Cena oferty brutto", "weight": 3}, {"phrase": "Nr oferty", "weight": 2},
             {"phrase": "złożyły oferty", "weight": 2}]
    kw, _ = W.infer_keywords(props, [text], "Informacja z otwarcia ofert")
    pats = list(kw)
    assert len(pats) == 1 + W.MAX_DOMAIN_KEYWORDS
    assert not any("dojazdu" in p for p in pats)  # unrelated to the title: ranked last, cut by the limit
    assert all("ofert" in p for p in pats)


# ---------------------------------------------------------------- one sample -> other documents of the same kind
OTWARCIE_SAMPLE = """=== Strona 1 ===
Urząd Miasta
Plac Przykładowy 8
Miasto 31.07.2025r.
IM.RZP.271.6.1.400.29.2025
INFORMACJA Z OTWARCIA OFERT
Wybór Wykonawcy zadania pn.: „Budowa żłobka w Mieście”
 Zamawiający informuje, iż na sfinansowanie zamówienia zamierza przeznaczyć 11.000.000,00 zł brutto.
Nr oferty Firma (nazwa) lub nazwisko
oraz adres wykonawcy Cena oferty brutto
1.
Budowlana Przykład sp. z o.o.
NIP 6912523110
11.927.917,89 zł brutto
ZATWIERDZAM
Z up. Prezydenta Miasta
"""
OTWARCIE_OTHER = """=== Strona 1 ===
Witaszyczki, 30-09-2021
Dotyczy: Rozbudowa Zakładu Zagospodarowania Odpadów. Numer postępowania: ZGO/ZP/18/2021
Informacja z otwarcia ofert
Działając na podstawie art. 222 ust. 5 ustawy Prawo zamówień publicznych Zamawiający przekazuje informacje o
wykonawcach, których oferty zostały otwarte, cenach lub kosztach zawartych w ofertach:
Nr Nazwa (firma) i adres Wykonawcy Wartość
1 Lider konsorcjum: Instalacje Przykład S.A. 91 979 400,00 PLN
"""
OTWARCIE_PROPOSAL = {  # what the 8B model proposed for the Legnica sample (fields shortened)
    "name": "informacja_z_otwarcia_ofert", "title": "INFORMACJA Z OTWARCIA OFERT",
    "description": "Dokument potwierdzający otwarcie ofert, z listą wykonawców i cen ofert brutto.",
    "not_this": "umowa ani wyrok",
    "keywords": [{"phrase": "INFORMACJA Z OTWARCIA OFERT", "weight": 5},
                 {"phrase": "Wybór Wykonawcy zadania pn.:", "weight": 3},
                 {"phrase": "Nr oferty Firma (nazwa) lub nazwisko oraz adres wykonawcy", "weight": 3},
                 {"phrase": "Cena oferty brutto", "weight": 3}, {"phrase": "ZATWIERDZAM", "weight": 3},
                 {"phrase": "Nr oferty", "weight": 2}, {"phrase": "NIP", "weight": 2}],
    "instructions": [],
    "fields": [{"path": "Zamawiajacy.nazwa", "type": "string", "description": "Nazwa.", "normalize": "strip",
                "values": [], "example": ""}],
}


def test_type_from_one_sample_classifies_another_issuers_document():
    from o2j.config import load_settings
    from o2j.spec import load_specs
    specs = load_specs(load_settings()["paths"]["doctypes"])
    ref = W.reference_texts(load_settings()["paths"].get("train"))
    spec, warns = W.build_inferred_spec(OTWARCIE_PROPOSAL, [OTWARCIE_SAMPLE], reference=ref, specs=specs)
    kw = spec["classify"]["keywords"]
    assert len(kw) <= 1 + W.MAX_DOMAIN_KEYWORDS
    assert not any(p.startswith("^") or "(?-i:" in p or "zatwierdzam" in p.lower() for p in kw)
    allspecs = {**specs, spec["name"]: W.load_spec_text(W.to_yaml(spec))}
    for text in (OTWARCIE_SAMPLE, OTWARCIE_OTHER):
        sc = rule_scores(text, "", allspecs)
        mine = sc.pop(spec["name"])
        assert mine >= 3 and mine - max(sc.values()) >= 2, sc  # confident, not "wygrywa Przelew"
    # never on the built-in types' own documents
    assert not any(rule_scores(t, "", allspecs)[spec["name"]] > 0 for _, t in ref)
    assert not any("wygrywa" in w or "nie wskazują" in w for w in warns)


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
    ref = W.reference_texts(load_settings()["paths"].get("train"), per_type=2)
    assert {t for t, _ in ref} == W.BUILTIN  # transfers are found as potwierdzenie_przelewu.pdf too
    # the example keywords do not fire on built-in reference documents
    kw, _ = W.infer_keywords(PROPOSAL["keywords"], [EXAMPLE], PROPOSAL["title"])
    assert not any(re.search(p, rule_text(t), flags=re.M | re.I) for p in kw for _, t in ref)
