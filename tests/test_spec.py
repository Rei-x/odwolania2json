import json

import pytest
from conftest import DOCTYPES, TRAIN
from jsonschema import Draft202012Validator

from eval.score import compare
from o2j import extract as E
from o2j.spec import load_specs

DOCTYPE_NAMES = sorted(p.stem for p in DOCTYPES.glob("*.yaml"))


def test_all_doctypes_loaded(specs):
    assert set(specs) == set(DOCTYPE_NAMES)
    assert {"odwolanie", "pelnomocnictwo", "przelew"} <= set(specs)
    for s in specs.values():
        assert s.description and s.fields
        assert s.classify.get("keywords"), f"{s.name}: no classification keywords"


@pytest.mark.parametrize("name", DOCTYPE_NAMES)
def test_json_schema_is_valid(specs, name):
    schema = specs[name].json_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(specs[name].fields)


def _shape(x):
    if isinstance(x, dict):
        return {k: _shape(v) for k, v in x.items()}
    return type(x).__name__


@pytest.mark.parametrize("name", DOCTYPE_NAMES)
def test_skeleton_matches_schema(specs, name):
    spec = specs[name]
    skel = spec.skeleton()
    Draft202012Validator(spec.json_schema()).validate(skel)
    assert list(skel) == list(spec.fields)  # key order preserved
    # skeleton is all-null / empty lists, so a postprocess of it is a fixpoint
    assert E.postprocess(spec, skel) == skel
    assert _shape(E.postprocess(spec, {})) == _shape(skel)


@pytest.mark.parametrize("name", DOCTYPE_NAMES)
def test_field_guide_non_empty(specs, name):
    guide = specs[name].field_guide()
    assert guide.strip()
    for top in specs[name].fields:
        assert f"- {top} " in guide


def test_enum_guide_lists_labels(specs):
    guide = specs["odwolanie"].field_guide()
    assert "9 = Decyzja o unieważnieniu postępowania" in guide


def _gold_files():
    out = []
    for name, spec in load_specs(DOCTYPES).items():
        js = (spec.raw.get("examples") or {}).get("json")
        if js:
            out += [(name, f) for f in sorted(TRAIN.glob(f"przyklad_*/{js}"))]
    return out


GOLD = _gold_files()
# Gold-data quirks (not code bugs): PESEL stored as a string in the reference JSON.
GOLD_SCHEMA_QUIRKS = {"przyklad_43/pelnomocnictwo.json"}


@pytest.mark.parametrize("name, path", [
    pytest.param(n, f, id=f"{f.parent.name}/{f.name}",
                 marks=[pytest.mark.xfail(reason="gold data: PESEL is a string, schema says integer")]
                 if f"{f.parent.name}/{f.name}" in GOLD_SCHEMA_QUIRKS else [])
    for n, f in GOLD
])
def test_gold_json_validates_against_schema(specs, name, path):
    Draft202012Validator(specs[name].json_schema()).validate(json.loads(path.read_text(encoding="utf-8")))


def test_gold_files_found():
    assert len(GOLD) >= 150


@pytest.mark.parametrize("name, path", [pytest.param(n, f, id=f"{f.parent.name}/{f.name}") for n, f in GOLD])
def test_postprocess_preserves_gold(specs, name, path):
    """Normalisation must not damage already-correct values (scored with the organiser metric)."""
    gold = json.loads(path.read_text(encoding="utf-8"))
    res = []
    compare(E.postprocess(specs[name], gold), gold, "", res)
    bad = [r for r in res if r[0] in ("FP", "FN")]
    assert not bad
