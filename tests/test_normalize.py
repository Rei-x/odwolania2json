import pytest

from o2j import normalize as N


@pytest.mark.parametrize("raw, expected", [
    ("2025-06-16", "2025-06-16"),
    (" 2025-6-3 ", "2025-06-03"),
    ("16.06.2025", "2025-06-16"),
    ("5.6.2025", "2025-06-05"),
    ("16-06-2025", "2025-06-16"),
    ("16/06/2025", "2025-06-16"),
    ("16 czerwca 2025 r.", "2025-06-16"),
    ("Warszawa, dnia 1 marca 2024", "2024-03-01"),
    ("3 września 2026", "2026-09-03"),
    ("1 październik 2025", "2025-10-01"),
    ("16 VI 2025", "2025-06-16"),
    ("2 xii 2025", "2025-12-02"),
])
def test_date_iso(raw, expected):
    assert N.date_iso(raw) == expected


@pytest.mark.parametrize("raw", ["31.02.2025", "16 XIII 2025", "16 foo 2025"])
def test_date_iso_invalid_returned_unchanged(raw):
    assert N.date_iso(raw) == raw


@pytest.mark.parametrize("raw", [None, "", "  ", "null", "brak", "-", "N/A"])
def test_empty_markers_become_none(raw):
    assert N.date_iso(raw) is None
    assert N.strip(raw) is None
    assert N.digits(raw) is None


@pytest.mark.parametrize("raw, expected", [
    ("15 000,00 zł", 15000.0),
    ("15 000,00 zł", 15000.0),
    ("7.500", 7500.0),
    ("15.000", 15000.0),
    ("7.500,00 PLN", 7500.0),
    ("15.000,50", 15000.5),
    ("1,234.56", 1234.56),
    ("1.5", 1.5),
    ("200,00", 200.0),
    ("10000", 10000.0),
    ("-3 000,00", 3000.0),
    ("- 200,00 PLN", 200.0),
    ("1 234,56 zł (słownie: tysiąc dwieście trzydzieści cztery 56/100)", 1234.56),
    (-50, 50.0),
    (12.345, 12.35),
    (200, 200.0),
])
def test_amount(raw, expected):
    assert N.amount(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "abc", "(słownie: sto złotych)", "brak"])
def test_amount_unparseable(raw):
    assert N.amount(raw) is None


def test_identifier_digits():
    assert N.nip("PL 999-928-40-65") == "9999284065"
    assert N.digits("REGON: 999 642 785") == "999642785"
    assert N.NORMALIZERS["regon"]("999-642-785") == "999642785"
    assert N.iban("PL 61 1090 1014 0000 0712 1981 2874") == "61109010140000071219812874"


@pytest.mark.parametrize("raw, expected", [
    ("405188", "0000405188"),
    ("KRS 0000405188", "0000405188"),
    ("0000 405 188", "0000405188"),
    ("12345678901", "12345678901"),  # longer than 10: left untouched
])
def test_krs_zero_padded(raw, expected):
    assert N.krs(raw) == expected


def test_integer_and_pesel():
    assert N.integer("PESEL 85010112345") == 85010112345
    assert N.NORMALIZERS["pesel"]("850-101-123-45") == 85010112345
    assert N.integer(True) == 1
    assert N.integer(3.9) == 3
    assert N.integer("brak") is None


@pytest.mark.parametrize("raw, expected", [
    ("2025/BZP 00123456/01", "2025/BZP00123456/01"),
    ("2025/BZP 123456", "2025/BZP00123456"),
    ("Ogłoszenie nr 2025/BZP 00543210", "2025/BZP00543210"),
    ("2025/bzp00012345", "2025/BZP00012345"),
    ("2026/BZP00999778", "2026/BZP00999778"),
])
def test_bzp(raw, expected):
    assert N.bzp(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("2025/S 112-383751", "383751-2025"),
    ("2025/S112 - 383751", "383751-2025"),
    ("383751-2025", "383751-2025"),
    ("Dz.U. S: 2026/S 055-999137", "999137-2026"),
    ("OJ S 107/2025 364525-2025", "364525-2025"),
])
def test_ted(raw, expected):
    assert N.ted(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("adw. Jan Kowalski", "Jan Kowalski"),
    ("adwokat Jan Kowalski", "Jan Kowalski"),
    ("r.pr. Anna Nowak", "Anna Nowak"),
    ("r. pr. Anna Nowak", "Anna Nowak"),
    ("radczyni prawna Anna Nowak", "Anna Nowak"),
    ("mec. Tomasz Wójcik", "Tomasz Wójcik"),
    ("apl. adw. Ewa Lis", "Ewa Lis"),
    ("aplikant adwokacki Ewa Lis", "Ewa Lis"),
    ("dr hab. Piotr Zieliński", "Piotr Zieliński"),
    ("prof. dr hab. Adam Mickiewicz", "Adam Mickiewicz"),
    ("Pani Maria Lis", "Maria Lis"),
    ("Jan Kowalski, adwokat", "Jan Kowalski"),
    ("Jan  Kowalski", "Jan Kowalski"),
    ("MARTYNA MIKUSEK", "Martyna Mikusek"),
    ("ANNA NOWAK-KOWALSKA", "Anna Nowak-Kowalska"),
    ("adw. ŁUKASZ ŻÓŁĆ", "Łukasz Żółć"),
    ("Jan McDonald", "Jan McDonald"),  # mixed case preserved
])
def test_person(raw, expected):
    assert N.person(raw) == expected


def test_person_radca_prawny():
    assert N.person("radca prawny Anna Nowak") == "Anna Nowak"


def test_city():
    assert N.city(" Warszawa, ") == "Warszawa"
    assert N.city(None) is None


def test_apply_uses_node_normalizers_and_type_defaults():
    assert N.apply("16.06.2025", {"type": "date"}) == "2025-06-16"
    assert N.apply("15 000,00", {"type": "number"}) == 15000.0
    assert N.apply("  a  b ", {"type": "string"}) == "a b"
    assert N.apply("405188", {"type": "string", "normalize": "krs"}) == "0000405188"
    assert N.apply("adw. JAN NOWAK", {"type": "string", "normalize": ["person"]}) == "Jan Nowak"
