"""Doctype wizard (o2j.wizard): organiser-style JSON template -> YAML spec -> validation. Offline, no LLM.

Asserted:
- every organiser template in data/schemas/*.json (JSON with // comments, sometimes missing commas) converts to a
  YAML spec that validates and loads through o2j.spec.load_specs, with the same top-level keys;
- types/normalisers inferred from values and field names (ISO date, KRS/NIP/REGON patterns, person, enum from comment);
- the three built-in config/doctypes/*.yaml validate without errors;
- validation errors carry the YAML line number;
- generated heading keywords are case-sensitive (a ruling that merely mentions the document must not match).
"""
import re
from pathlib import Path

import pytest
from conftest import DOCTYPES, ROOT

from o2j import wizard as W

SCHEMAS = sorted((ROOT / "data" / "schemas").glob("*.json"))


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.stem)
def test_organiser_templates_roundtrip(path: Path):
    tpl = path.read_text(encoding="utf-8")
    spec = W.draft("tmp_" + path.stem, "Dokument testowy", "", template=tpl)
    text = W.to_yaml(spec)
    v = W.validate(text)
    assert v["ok"], v["errors"]
    loaded = W.load_spec_text(text)
    assert list(loaded.skeleton()) == [k for k, _, _ in W.parse_template(tpl)[1]]


def test_inference_from_values_names_and_comments():
    f = W.fields_from_template("""{
      "Sprawa": {
        "data": "2025-10-13", // Data pisma.
        "kwota": 1500.5,
        "krs": null, // KRS
        "przez-pelnomocnika": 1, //1- tak, 0- nie
        "typ": "osoba_prawna" // "osoba_prawna" lub "osoba_fizyczna"
        "rachunek": null
      },
      "pelnomocnicy": [{"imie_nazwisko": "Jan Kowalski"}]
    }""")
    s = f["Sprawa"]["properties"]
    assert s["data"]["type"] == "date" and s["data"]["description"] == "Data pisma."
    assert s["kwota"]["type"] == "number" and s["kwota"]["normalize"] == ["amount"]
    assert s["krs"]["normalize"] == ["krs"] and s["krs"]["pattern"] == r"\d{10}"
    assert s["przez-pelnomocnika"]["type"] == "enum" and [v["value"] for v in s["przez-pelnomocnika"]["values"]] == [1, 0]
    assert s["typ"]["values"] == ["osoba_prawna", "osoba_fizyczna"]
    assert s["rachunek"]["normalize"] == ["iban"]
    p = f["pelnomocnicy"]
    assert p["type"] == "array" and p["dedupe"] == "person"
    assert p["items"]["properties"]["imie_nazwisko"]["normalize"] == ["person"]


def test_field_table_rows():
    f = W.fields_from_table([
        {"name": "nip_sprzedawcy", "type": "string", "normalize": "auto"},
        {"name": "forma", "type": "enum", "values": "1=przelew, 2=gotówka"},
        {"name": "pozycje", "type": "array", "children": [{"name": "wartosc", "type": "number", "normalize": "amount"}]},
    ])
    assert f["nip_sprzedawcy"]["normalize"] == ["nip"]
    assert f["forma"]["values"] == [{"value": 1, "label": "przelew"}, {"value": 2, "label": "gotówka"}]
    assert f["pozycje"]["items"]["properties"]["wartosc"]["normalize"] == ["amount"]


@pytest.mark.parametrize("path", sorted(DOCTYPES.glob("*.yaml")), ids=lambda p: p.stem)
def test_builtin_doctypes_validate(path: Path):
    v = W.validate(path.read_text(encoding="utf-8"))
    assert v["ok"], v["errors"]


def test_errors_have_line_numbers():
    v = W.validate("name: faktura\ndescription: x\nfields:\n  a: {type: strng}\n  b: {type: string, normalize: [foo]}\n")
    assert not v["ok"]
    assert {e["line"] for e in v["errors"]} == {4, 5}
    v = W.validate("name: x\nfields: [\n")
    assert not v["ok"] and v["errors"][0]["line"]


def test_template_syntax_error_line():
    with pytest.raises(W.TemplateError) as e:
        W.parse_template('{\n  "a": 1,\n  "b": }\n')
    assert e.value.line == 3


def test_heading_keyword_is_case_sensitive():
    kw = W.suggest_classify("przystapienie", "Przystąpienie do postępowania odwoławczego", "")["keywords"]
    head = next(iter(kw))
    flags = re.M | re.I  # as in o2j.classify.rule_scores
    assert re.search(head, "PRZYSTĄPIENIE DO POSTĘPOWANIA ODWOŁAWCZEGO", flags)
    assert not re.search(head, "Izba ustaliła, że przystąpienie zgłosił wykonawca", flags)
