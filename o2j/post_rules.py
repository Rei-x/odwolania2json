"""Deterministic fixes applied to the final JSON, each grounded in the document text.

- city names: a known Polish city with lost diacritics ("Lódź", "Lodz") -> canonical spelling ("Łódź");
- one identifier, one party: a NIP/REGON/KRS copied onto several parties of a list stays only with the party
  the document puts it next to;
- transfer date: a date taken from a receipt stamp ("WPŁYNĘŁO dnia …") or a print timestamp is replaced by the
  date the confirmation labels as the operation/transaction date;
- sole trader: "X, prowadzący działalność gospodarczą pod firmą …" -> natural person X;
- account numbers: no whitespace, with the country code ("PL…") only when the document writes it (organiser's rule).
Every rule only acts when the text clearly supports it; otherwise the value is left as the model returned it.
"""
from __future__ import annotations

import re

from .doc_order import doc_text, fold

CITIES = """Białystok Bielsko-Biała Bydgoszcz Bytom Chełm Chorzów Częstochowa Dąbrowa Górnicza Elbląg Gdańsk Gdynia
Gliwice Głogów Gniezno Gorzów Wielkopolski Grudziądz Jastrzębie-Zdrój Jaworzno Jelenia Góra Kalisz Katowice Kielce
Konin Koszalin Kraków Krosno Legnica Leszno Lublin Łomża Łódź Mielec Mysłowice Nowy Sącz Olsztyn Opole Ostrołęka
Ostrów Wielkopolski Piekary Śląskie Piła Piotrków Trybunalski Płock Poznań Przemyśl Pruszków Radom Ruda Śląska Rybnik
Rzeszów Siedlce Siemianowice Śląskie Skierniewice Słupsk Sopot Sosnowiec Stalowa Wola Starogard Gdański Suwałki
Szczecin Świdnica Świętochłowice Tarnobrzeg Tarnów Tczew Toruń Tychy Wałbrzych Warszawa Włocławek Wrocław Zabrze
Zamość Zawiercie Zgierz Zielona Góra Żory Żyrardów Bełchatów Biała Podlaska Brzeg Ciechanów Inowrocław Jarosław
Kędzierzyn-Koźle Kołobrzeg Kutno Łuków Malbork Mińsk Mazowiecki Nysa Oświęcim Pabianice Puławy Racibórz Sandomierz
Sanok Sieradz Skarżysko-Kamienna Starachowice Szczecinek Świnoujście Tomaszów Mazowiecki Wejherowo Wodzisław Śląski
Zakopane Żagań Żary Ełk Giżycko Kętrzyn Augustów Bolesławiec Chojnice Gniew Końskie Łańcut Łask Łęczyca Łowicz
Łuków Ostrowiec Świętokrzyski Otwock Pszczyna Sochaczew Środa Wielkopolska Śrem Świebodzin Wągrowiec Września
Wołomin Zduńska Wola Żywiec Brzozów Dębica Gorlice Jasło Józefów Lębork Łobez Mława Myszków Olkusz Opoczno
Pułtusk Rawicz Sulejówek Szamotuły Turek Wieliczka Ząbki Zielonka Łomianki Piaseczno Legionowo Marki Kobyłka"""

_CITY_LIST: list[str] = []
for line in CITIES.split("\n"):
    _CITY_LIST += [c for c in re.split(r"\s(?=[A-ZŁŚŻŹĆ])", line.strip())]
# multi-word names were split above; rebuild them from a fixed list of known compounds
_COMPOUNDS = ["Dąbrowa Górnicza", "Gorzów Wielkopolski", "Jelenia Góra", "Nowy Sącz", "Ostrów Wielkopolski",
              "Piekary Śląskie", "Piotrków Trybunalski", "Ruda Śląska", "Siemianowice Śląskie", "Stalowa Wola",
              "Starogard Gdański", "Zielona Góra", "Biała Podlaska", "Mińsk Mazowiecki", "Tomaszów Mazowiecki",
              "Wodzisław Śląski", "Ostrowiec Świętokrzyski", "Środa Wielkopolska", "Zduńska Wola"]
CITY_BY_FOLD = {fold(c): c for c in _CITY_LIST + _COMPOUNDS if c}

ID_KEYS = ("nip", "regon", "krs")
_DATE = r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})|(\d{4})-(\d{2})-(\d{2})"
OP_LABEL = re.compile(r"data\s+(?:operacji|transakcji|wykonania|realizacji|ksiegowania|zlecenia|przelewu)\s*:?\s*(?:" + _DATE + ")")
STAMP_CTX = re.compile(r"(?:wplynel\w*|wplyw\w*|wygenerowan\w*|wydruk\w*|l\.\s*dz)[^0-9]{0,25}$")
SOLE = re.compile(r"([a-z][a-z\-]+\s+[a-z][a-z\-]+)\s*,?\s*prowadzac\w*(?:\s*/\s*a)?\s+(?:jednoosobow\w+\s+)?"
                  r"dzialalnosc\w*\s+gospodarcz\w*")


def _iso(m: re.Match) -> str | None:
    g = m.groups()[-6:]
    if g[0]:
        d, mo, y = int(g[0]), int(g[1]), int(g[2])
    else:
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _date_contexts(text: str, iso: str) -> list[str]:
    """The ~40 characters before every occurrence of the date `iso` in the folded text."""
    y, mo, d = iso.split("-")
    pats = [rf"\b0?{int(d)}[.\-/]0?{int(mo)}[.\-/]{y}\b", rf"\b{y}-{mo}-{d}\b",
            rf"\b0?{int(d)}\s+{MONTHS[int(mo) - 1]}\s+{y}\b"]
    out = []
    for p in pats:
        out += [text[max(0, m.start() - 40):m.start()] for m in re.finditer(p, text)]
    return out


def fix_cities(node, changes: list, path: str = ""):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k == "miejscowosc" and isinstance(v, str):
                canon = CITY_BY_FOLD.get(fold(v.strip()))
                if canon and canon != v.strip():
                    changes.append({"rule": "city", "field": p, "before": v, "after": canon})
                    node[k] = canon
            else:
                fix_cities(v, changes, p)
    elif isinstance(node, list):
        for i, x in enumerate(node):
            fix_cities(x, changes, f"{path}[{i}]")


def _party_data(item):
    return item.get("data") if isinstance(item, dict) and isinstance(item.get("data"), dict) else item


def _name_positions(text: str, name) -> list[int]:
    if not isinstance(name, str) or len(name.strip()) < 3:
        return []
    words = re.findall(r"[a-z0-9]+", fold(name))[:4]
    if not words:
        return []
    pat = r"\W+".join(re.escape(w) for w in words)
    return [m.start() for m in re.finditer(pat, text)]


def fix_shared_ids(result: dict, text: str, changes: list):
    """In every list of parties, an identifier present on several parties stays with the one whose name
    most closely precedes the identifier in the text."""
    for key, lst in result.items():
        if not isinstance(lst, list) or len(lst) < 2:
            continue
        datas = [_party_data(x) for x in lst]
        if not all(isinstance(d, dict) for d in datas):
            continue
        for idk in ID_KEYS:
            vals = [str(d.get(idk) or "") for d in datas]
            for v in {x for x in vals if x}:
                holders = [i for i, x in enumerate(vals) if x == v]
                if len(holders) < 2:
                    continue
                id_pos = [m.start() for m in re.finditer(re.escape(v), re.sub(r"[\s\-]", "", text))]
                # positions in the de-spaced text are close enough to the folded text for ordering on one page
                if not id_pos:
                    continue
                flat = re.sub(r"[\s\-]", "", text)
                best, best_gap = None, None
                for i in holders:
                    for np_ in _name_positions(flat, re.sub(r"\s", "", datas[i].get("nazwa") or "")):
                        for ip in id_pos:
                            gap = ip - np_
                            if 0 <= gap and (best_gap is None or gap < best_gap):
                                best, best_gap = i, gap
                if best is None or best_gap is None or best_gap > 600:
                    continue
                for i in holders:
                    if i != best:
                        changes.append({"rule": "shared_id", "field": f"{key}[{i}].{idk}", "before": v, "after": None})
                        datas[i][idk] = None


def fix_transfer_date(result: dict, text: str, changes: list):
    pb = result.get("przelew_bankowy")
    if not isinstance(pb, dict) or not isinstance(pb.get("data_operacji"), str):
        return
    cur = pb["data_operacji"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cur):
        return
    ctx = _date_contexts(text, cur)
    if not ctx or not all(STAMP_CTX.search(c) for c in ctx):
        return  # the current date also appears outside a stamp: keep it
    labelled = [_iso(m) for m in OP_LABEL.finditer(text)]
    labelled = [d for d in labelled if d and d != cur]
    if labelled:
        changes.append({"rule": "transfer_date", "field": "przelew_bankowy.data_operacji", "before": cur,
                        "after": labelled[0]})
        pb["data_operacji"] = labelled[0]


SOLE_RAW = re.compile(r"([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\-]+)\s*,?\s*prowadząc\w*(?:\s*/\s*a)?\s+"
                      r"(?:jednoosobow\w+\s+)?działalnoś\w*\s+gospodarcz\w*")


def fix_sole_trader(result: dict, text: str, changes: list, raw: str = ""):
    mocs = result.get("mocodawca")
    if not isinstance(mocs, list):
        return
    m = SOLE.search(text)
    if not m:
        return
    person = m.group(1)
    mr = SOLE_RAW.search(raw or "")
    person_raw = mr.group(1) if mr and fold(mr.group(1)) == person else None
    for i, it in enumerate(mocs):
        d = _party_data(it)
        if not isinstance(d, dict):
            continue
        hay = fold(" ".join(str(d.get(k) or "") for k in ("imie_nazwisko", "nazwa")))
        if person not in hay:
            continue
        if d.get("typ") != "osoba_fizyczna" and "typ" in d:
            changes.append({"rule": "sole_trader", "field": f"mocodawca[{i}].data.typ", "before": d.get("typ"),
                            "after": "osoba_fizyczna"})
            d["typ"] = "osoba_fizyczna"
        if "imie_nazwisko" in d and fold(str(d.get("imie_nazwisko") or "")) != person:
            name = person_raw
            if not name:  # original spelling from the party's own name
                words = str(d.get("nazwa") or "").split()
                name = next((" ".join(words[j:j + 2]) for j in range(len(words) - 1)
                             if fold(" ".join(words[j:j + 2])) == person), None)
            if name:
                changes.append({"rule": "sole_trader", "field": f"mocodawca[{i}].data.imie_nazwisko",
                                "before": d.get("imie_nazwisko"), "after": name})
                d["imie_nazwisko"] = name


MONTHS = "stycznia lutego marca kwietnia maja czerwca lipca sierpnia wrzesnia pazdziernika listopada grudnia".split()
_DMY = r"(\d{1,2})[ .](\d{1,2}|[a-z]+)[ .](\d{4})"
ACT_DATE = [re.compile(r"zamawiajacy\s+w\s+dniu\s+" + _DMY),
            re.compile(r"(?:zaskarzon\w*\s+)?czynnosc\w*\s+(?:zamawiajacego\s+)?(?:zostala\s+)?(?:opublikowan\w*|przekazan\w*|dokonan\w*|doreczon\w*)?\s*(?:w\s+dniu|dnia)\s+" + _DMY)]
ACT_CUE = re.compile(r"zamawiajacy\s+w\s+dniu\s+\S+\s+\S+\s+\d{4}\s*(?:r\.|roku)?\s*nie\s+(wykluczyl|odrzucil)")
CUE_REASON = {"wykluczyl": (8, "Zaniechanie wykluczenia wykonawcy"), "odrzucil": (7, "Zaniechanie odrzucenia oferty")}


def _dmy_iso(d, mo, y):
    if mo.isdigit():
        mo_i = int(mo)
    elif mo in MONTHS:
        mo_i = MONTHS.index(mo) + 1
    else:
        return None
    if not (1 <= mo_i <= 12 and 1 <= int(d) <= 31):
        return None
    return f"{int(y):04d}-{mo_i:02d}-{int(d):02d}"


def fix_act(result: dict, text: str, changes: list):
    """Appeal: the date of the contested act ("Zamawiający w dniu 8 lipca 2026 roku …", "czynność opublikowana
    w dniu 11.05.2026") when the model left it empty or took it from a stamp; the reason when the act sentence
    says it outright ("… nie wykluczył" -> 8, "… nie odrzucił" -> 7; 16/16 agreement with the reference data)."""
    od = result.get("OdwolanieKIO")
    if not isinstance(od, dict):
        return
    cur = od.get("czynnosc_dzien")
    stale = not cur or not isinstance(cur, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cur)
    if not stale:
        ctx = _date_contexts(text, cur)
        stale = not ctx or all(STAMP_CTX.search(c) or re.search(r"data\s*:?\s*$", c) for c in ctx)
    if stale:
        for rx in ACT_DATE:
            m = rx.search(text)
            iso = _dmy_iso(*m.groups()[-3:]) if m else None
            if iso:
                if iso != cur:
                    changes.append({"rule": "act_date", "field": "OdwolanieKIO.czynnosc_dzien", "before": cur, "after": iso})
                    od["czynnosc_dzien"] = iso
                break
    m = ACT_CUE.search(text)
    if m and "czynnosc_powod_id" in od:
        rid, label = CUE_REASON[m.group(1)]
        if od.get("czynnosc_powod_id") != rid:
            changes.append({"rule": "act_reason", "field": "OdwolanieKIO.czynnosc_powod_id",
                            "before": od.get("czynnosc_powod_id"), "after": rid})
            od["czynnosc_powod_id"] = rid
            if "czynnosc_opis" in od:
                od["czynnosc_opis"] = label
        elif "czynnosc_opis" in od and not od.get("czynnosc_opis"):
            changes.append({"rule": "act_reason", "field": "OdwolanieKIO.czynnosc_opis", "before": None, "after": label})
            od["czynnosc_opis"] = label


ACCOUNT_KEYS = ("z_rachunku", "na_rachunek")


def fix_country_codes(result: dict, raw: str, changes: list):
    pb = result.get("przelew_bankowy")
    if not isinstance(pb, dict):
        return
    flat = re.sub(r"\s", "", raw)
    for k in ACCOUNT_KEYS:
        v = pb.get(k)
        if not isinstance(v, str):
            continue
        m = re.fullmatch(r"([A-Za-z]{2})?(\d{26})", re.sub(r"\s", "", v))
        if not m:
            continue
        digits = m.group(2)
        codes = {flat[i - 2:i] for i in (x.start() for x in re.finditer(digits, flat)) if i >= 2}
        letters = {c for c in codes if re.fullmatch(r"[A-Z]{2}", c)}
        positions = [x.start() for x in re.finditer(digits, flat)]
        if not positions:
            continue  # number not found verbatim in the text: leave as is
        new = (sorted(letters)[0] + digits) if letters else digits
        if new != v:
            changes.append({"rule": "account_country_code", "field": f"przelew_bankowy.{k}", "before": v, "after": new})
            pb[k] = new


def apply(result: dict, doc) -> list[dict]:
    if not isinstance(result, dict):
        return []
    changes: list[dict] = []
    fix_cities(result, changes)
    if doc is not None and getattr(doc, "pages", None):
        text = doc_text(doc)
        if text.strip():
            fix_shared_ids(result, text, changes)
            fix_transfer_date(result, text, changes)
            fix_act(result, text, changes)
            fix_sole_trader(result, text, changes, "\n".join(p.text for p in doc.pages))
        fix_country_codes(result, "\n".join(p.text for p in doc.pages), changes)
    return changes
