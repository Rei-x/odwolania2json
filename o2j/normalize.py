"""Deterministic normalizers referenced by name from doctype YAML (`normalize: [...]`)."""
from __future__ import annotations

import re
from datetime import date

MONTHS = {
    "stycznia": 1, "styczeń": 1, "lutego": 2, "luty": 2, "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4, "maja": 5, "maj": 5, "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7, "sierpnia": 8, "sierpień": 8, "września": 9, "wrzesień": 9,
    "października": 10, "październik": 10, "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12,
}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
         "ix": 9, "x": 10, "xi": 11, "xii": 12}


def _s(v):
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def strip(v):
    s = _s(v)
    if s and s.lower() in {"null", "none", "brak", "n/a", "-", "—"}:
        return None
    return s


def digits(v):
    s = strip(v)
    if s is None:
        return None
    d = re.sub(r"\D", "", s)
    return d or None


def krs(v):
    d = digits(v)
    return d.zfill(10) if d and len(d) <= 10 else d


def nip(v):
    d = digits(v)
    return d


def iban(v):
    """Polish account: 26 digits without PL prefix/spaces."""
    d = digits(v)
    return d


def bzp(v):
    s = strip(v)
    if s is None:
        return None
    s = re.sub(r"\s+", "", s).upper()
    m = re.search(r"(\d{4})/BZP0*?(\d{6,8})(/\d{1,2})?", s)
    if m:
        year, num, corr = m.group(1), m.group(2), m.group(3) or ""
        return f"{year}/BZP{num.zfill(8)}{corr}"
    return s


def ted(v):
    s = strip(v)
    if s is None:
        return None
    m = re.search(r"(\d{4})/S\s*\d{1,3}\s*-\s*(\d{5,7})", s)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    m = re.search(r"(\d{5,7})\s*-\s*(\d{4})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def date_iso(v):
    s = strip(v)
    if s is None:
        return None
    s_low = s.lower()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s_low)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s_low)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            m = re.search(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", s_low)
            if m and m.group(2) in MONTHS:
                d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
            else:
                m = re.search(r"(\d{1,2})\s+([ivx]+)\s+(\d{4})", s_low)
                if m and m.group(2) in ROMAN:
                    d, mo, y = int(m.group(1)), ROMAN[m.group(2)], int(m.group(3))
                else:
                    return s
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return s


def amount(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(abs(float(v)), 2)  # debit shown as "-3 000,00" -> amount is positive
    s = strip(v)
    if s is None:
        return None
    s = s.split("(")[0].replace("-", "")  # drop "(słownie: ...)"
    s = re.sub(r"[^\d,.\-]", "", s.replace("\u00a0", ""))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # 7.500 / 15.000 -> thousands separators
        s = s.replace(".", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def integer(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    d = digits(v)
    return int(d) if d else None


TITLES = r"(mecenas|aplikant(ka)?\s+(adwokack[ia]|radcowsk[ia])|adw\.?|adwokat|r\.\s?pr\.?|radca\s+prawny|radczyni\s+prawna|radca|mec\.?|dr\.?\s*hab\.?|dr\.?|prof\.?|apl\.?\s*adw\.?|apl\.?\s*radc\.?|pan|pani|mgr\.?|inż\.?)"


def person(v):
    s = strip(v)
    if s is None:
        return None
    prev = None
    while prev != s:
        prev = s
        s = re.sub(rf"^{TITLES}\s+", "", s, flags=re.I)
        s = re.sub(rf",?\s+{TITLES}$", "", s, flags=re.I)
    s = s.strip(" ,")
    if s and s.isupper() and len(s) > 3:  # "MARTYNA MIKUSEK" -> "Martyna Mikusek"
        s = "-".join(w.capitalize() for w in s.lower().split("-"))
        s = " ".join(w[:1].upper() + w[1:] for w in s.split(" "))
    return s or None


def city(v):
    s = strip(v)
    return s.strip(" ,") if s else None


NORMALIZERS = {
    "strip": strip, "digits": digits, "krs": krs, "nip": nip, "regon": digits,
    "pesel": integer, "iban": iban, "bzp": bzp, "ted": ted, "date": date_iso,
    "amount": amount, "integer": integer, "person": person, "city": city,
}

DEFAULT_BY_TYPE = {"date": ["date"], "number": ["amount"], "integer": ["integer"], "string": ["strip"]}


def apply(value, node: dict):
    names = node.get("normalize") or DEFAULT_BY_TYPE.get(node["type"], [])
    if isinstance(names, str):
        names = [names]
    for n in names:
        value = NORMALIZERS[n](value)
    return value
