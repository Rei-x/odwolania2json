"""Frozen BLIND test set: 20 synthetic cases "generated from real cases" (unused training cases).

For every case:
  1. a source case is drawn (seeded) from data/train cases NOT used by eval/make_variants.py;
     its *structure* is inherited (reason id, #attorneys, consortium / multi-contracting-authority /
     sole trader, presence of header date and BZP/TED numbers),
  2. all *facts* are re-drawn (company names, people, identifiers, dates, titles, amounts, accounts),
  3. 1-3 difficulties are drawn (seeded, coverage-balanced) from a broad pool, plus a random
     baseline style (law-firm phrasing, header format, bank profile, fonts),
  4. ground truth is built programmatically from the facts (never by the LLM),
  5. an LLM writes each document from scratch from the facts + GT + layout instructions,
     using the source training document only as a genre reference,
  6. the markup is rendered to PDF (reportlab, per-document fonts/margins),
  7. automatic checks: every GT value / exact required string present, nulls absent,
     no foreign identifiers or dates, no leakage of source-case names; failures are regenerated
     with feedback.

Output: data/blind/blind_NN/{odwolanie,pelnomocnictwo,potwierdzenie_przelewu}.pdf + GT JSONs
        data/blind/_manifest.json (what each case tests), data/blind/_build/ (markup, checks, costs)

Usage: python -m eval.make_blind [--only blind_03 ...] [--force] [--workers 6] [--plan]
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.make_variants import check as gt_check  # noqa: E402  (read-only reuse)

TRAIN = ROOT / "data" / "train"
OUT = ROOT / "data" / "blind"
BUILD = OUT / "_build"
SEED = 20261121
N_CASES = 20
MODEL = "moonshotai/kimi-k3.1-pro"
USED_BY_VARIANTS = {2, 3, 5, 7, 10, 12, 15, 18, 21, 26, 30, 35, 47, 53, 57}
DOCS = {"odwolanie": ("odwolanie.pdf", "odwolanie.json"),
        "pelnomocnictwo": ("pelnomocnictwo.pdf", "pelnomocnictwo.json"),
        "przelew": ("potwierdzenie_przelewu.pdf", "przelew.json")}
POWOD = {1: "Decyzja o odrzuceniu oferty", 2: "Ogłoszenie wyboru oferty", 3: "Decyzja o wykluczeniu wykonawcy",
         4: "Publikacja specyfikacji warunków zamówienia (SWZ)", 5: "Modyfikacja treści SWZ",
         6: "Odpowiedzi/wyjaśnienia do SWZ", 7: "Zaniechanie odrzucenia oferty",
         8: "Zaniechanie wykluczenia wykonawcy", 9: "Decyzja o unieważnieniu postępowania",
         10: "Zaniechanie unieważnienia postępowania", 11: "Opis przedmiotu zamówienia (OPZ)",
         12: "Projektowane postanowienia umowy"}  # official dictionary: data/schemas/czynnosc_powod_id_dict.md
# reason 12 is absent from training data; a few blind cases with an SWZ-type source are switched to it
POWOD_OVERRIDE: dict[str, int] = {}

# ============================================================================ pools
FIRST_M = ["Adam", "Bartłomiej", "Cezary", "Damian", "Dariusz", "Edward", "Filip", "Grzegorz", "Henryk", "Igor",
           "Jacek", "Jakub", "Jerzy", "Kamil", "Konrad", "Krzysztof", "Leszek", "Łukasz", "Maciej", "Marcin",
           "Mariusz", "Mateusz", "Michał", "Mikołaj", "Norbert", "Oskar", "Paweł", "Przemysław", "Radosław",
           "Robert", "Sebastian", "Stanisław", "Szymon", "Tadeusz", "Wiktor", "Witold", "Zbigniew", "Wojciech"]
FIRST_F = ["Agata", "Alicja", "Anna", "Beata", "Bożena", "Danuta", "Dominika", "Edyta", "Elżbieta", "Ewelina",
           "Gabriela", "Hanna", "Iwona", "Izabela", "Joanna", "Justyna", "Karolina", "Katarzyna", "Kinga",
           "Lidia", "Magdalena", "Marta", "Monika", "Natalia", "Paulina", "Renata", "Sylwia", "Teresa",
           "Urszula", "Weronika", "Zofia", "Żaneta", "Aleksandra", "Malwina"]
LAST = ["Andrzejewski", "Bielecki", "Borowski", "Chmielewski", "Czarnecki", "Dąbrowski", "Gajewski", "Głowacki",
        "Jankowski", "Kalinowski", "Kołodziejski", "Kowalewski", "Krajewski", "Laskowski", "Lewandowski",
        "Makowski", "Michalski", "Nowicki", "Olszewski", "Pietrzycki", "Rogalski", "Sadowski", "Sobolewski",
        "Szczepański", "Tomaszewski", "Wasilewski", "Zalewski", "Żurawski", "Wierzbicki", "Grabowiecki",
        "Nowak", "Wójcik", "Kowalczyk", "Mazur", "Krawczyk", "Pawlak", "Zając", "Król", "Wróbel", "Dudek",
        "Sikora", "Baran", "Kubiak", "Wilk", "Kozieł", "Ostrowiak", "Gołąb", "Szewczyk", "Kaczmarczyk", "Bąk",
        "Lis", "Jaworek", "Pietrzak", "Urban", "Sowa", "Kmieć", "Cichoń", "Domagała", "Nawrocki", "Żak"]
STEMS = ["Velmora", "Kastrel", "Orvenia", "Branthis", "Lumexa", "Tervalis", "Quorvent", "Silvanta", "Morvex",
         "Delcora", "Haldrin", "Ostravia", "Pentrix", "Wirtana", "Zelmar", "Krovent", "Altheris", "Nerova",
         "Brisca", "Travello", "Cyrenix", "Galvora", "Mirkon", "Rotavia", "Fennix", "Ardento", "Solvadi",
         "Ternum", "Varsko", "Elbrix", "Domvar", "Kelvio", "Marbex", "Pyrgos", "Ulvena", "Zortan", "Grevil",
         "Hexalia", "Inveron", "Lorvik"]
SECTORS = ["Budownictwo", "Systemy IT", "Infrastruktura", "Medical", "Energia", "Logistyka", "Serwis",
           "Technologie", "Instalacje", "Drogi i Mosty", "Facility Management", "Ekologia", "Automatyka",
           "Inżynieria", "Laboratoria", "Telekom", "Projekt", "Utrzymanie Zieleni", "Transport", "Data Center"]
FORMS = ["sp. z o.o.", "sp. z o.o.", "S.A.", "sp. z o.o. sp.k.", "sp.j.", "Spółka Akcyjna",
         "Spółka z ograniczoną odpowiedzialnością", "sp. k."]
TOWNS = [("Lisowo", "Lisowie"), ("Bramów", "Bramowie"), ("Dębogóra", "Dębogórze"), ("Kaliszany", "Kaliszanach"),
         ("Rudnik Górny", "Rudniku Górnym"), ("Zawierzyce", "Zawierzycach"), ("Sokolniki Nowe", "Sokolnikach Nowych"),
         ("Grabin", "Grabinie"), ("Wierzbnica", "Wierzbnicy"), ("Olszany", "Olszanach"), ("Przytoczno", "Przytocznie"),
         ("Jeziorany Małe", "Jezioranach Małych"), ("Borzęcin Dolny", "Borzęcinie Dolnym"), ("Krzemienica", "Krzemienicy"),
         ("Strzelin Wielki", "Strzelinie Wielkim"), ("Mokrany", "Mokranach"), ("Czarnolesie", "Czarnolesiu"),
         ("Wolbórz Nowy", "Wolborzu Nowym"), ("Radzików", "Radzikowie"), ("Łęgowo", "Łęgowie")]
CITIES = [("Warszawa", "0"), ("Kraków", "3"), ("Gdańsk", "8"), ("Poznań", "6"), ("Wrocław", "5"), ("Łódź", "9"),
          ("Lublin", "2"), ("Katowice", "4"), ("Bydgoszcz", "8"), ("Szczecin", "7"), ("Rzeszów", "3"),
          ("Olsztyn", "1"), ("Białystok", "1"), ("Kielce", "2"), ("Opole", "4"), ("Toruń", "8"), ("Gliwice", "4"),
          ("Płock", "0"), ("Zielona Góra", "6"), ("Radom", "2"), ("Częstochowa", "4"), ("Elbląg", "8"),
          ("Tarnów", "3"), ("Koszalin", "7"), ("Siedlce", "0"), ("Nowy Sącz", "3")]
STREETS = ["Lipowa", "Kwiatowa", "Przemysłowa", "Fabryczna", "Kolejowa", "Ogrodowa", "Słoneczna", "Polna",
           "Grunwaldzka", "Mickiewicza", "Sienkiewicza", "Kościuszki", "Piłsudskiego", "Wojska Polskiego",
           "Armii Krajowej", "Jana Pawła II", "Szkolna", "Leśna", "Długa", "Krótka", "Rynek", "Hutnicza",
           "Inżynierska", "Składowa", "Graniczna", "al. Niepodległości", "pl. Wolności", "Toruńska", "Portowa"]
PATRONS = ["św. Łukasza", "Mikołaja Kopernika", "Marii Skłodowskiej-Curie", "dr. Władysława Biegańskiego",
           "Ludwika Rydygiera", "Jana Śniadeckiego"]
TITLES = [
    "Przebudowa drogi powiatowej nr 1452 wraz z budową chodnika i kanalizacji deszczowej na odcinku {T} – {T2}",
    "Dostawa sprzętu komputerowego i oprogramowania biurowego dla jednostek organizacyjnych",
    "Świadczenie usług odbioru i zagospodarowania odpadów komunalnych z terenu nieruchomości zamieszkałych",
    "Budowa stacji uzdatniania wody wraz z siecią wodociągową w miejscowości {T}",
    "Kompleksowe utrzymanie czystości w budynkach szpitala wraz z dezynfekcją pomieszczeń",
    "Dostawa tomografu komputerowego 128-warstwowego wraz z adaptacją pomieszczenia pracowni",
    "Termomodernizacja budynków użyteczności publicznej wraz z montażem instalacji fotowoltaicznych",
    "Zakup i dostawa autobusów elektrycznych wraz z infrastrukturą ładowania",
    "Wdrożenie zintegrowanego systemu informatycznego klasy ERP wraz z usługą utrzymania",
    "Zimowe utrzymanie dróg wojewódzkich w sezonach 2026/2027 i 2027/2028",
    "Dostawa energii elektrycznej do obiektów i punktów poboru zamawiającego",
    "Rozbudowa oczyszczalni ścieków wraz z modernizacją części osadowej",
    "Usługa ochrony fizycznej osób i mienia oraz monitoringu obiektów",
    "Dostawa odczynników laboratoryjnych wraz z dzierżawą analizatorów biochemicznych",
    "Budowa hali sportowej z zapleczem szatniowym przy szkole podstawowej w {T}",
    "Modernizacja oświetlenia ulicznego na terenie gminy z zastosowaniem technologii LED",
    "Świadczenie usług przewozu uczniów do szkół w roku szkolnym 2026/2027",
    "Dostawa i montaż wyposażenia pracowni dydaktycznych w ramach projektu edukacyjnego",
    "Opracowanie dokumentacji projektowej rewitalizacji centrum miejscowości {T}",
    "Rozbudowa sieci światłowodowej oraz dostawa urządzeń aktywnych sieci LAN",
    "Przebudowa ujęcia wody i budowa zbiornika retencyjnego w {Tloc}",
    "Pełnienie funkcji inżyniera kontraktu dla zadania budowy obwodnicy {Tgen}",
    "Dostawa paliw płynnych do pojazdów i urządzeń zamawiającego w formie bezgotówkowej",
    "Usługa kompleksowego żywienia pacjentów szpitala",
    "Remont dachu i elewacji zabytkowego budynku ratusza w {Tloc}",
]
WINNER_ROLES = ["wykonawca, którego oferta została wybrana", "przystępujący po stronie Zamawiającego",
                "wykonawca sklasyfikowany na drugim miejscu"]
FUNCTIONS = ["Prezes Zarządu", "Wiceprezes Zarządu", "Członek Zarządu", "Prokurent", "Wspólnik uprawniony do reprezentacji",
             "Komplementariusz"]
BANKS = [
    dict(name="Bank Nadwiślański S.A.", nr="CEN", layout="tabela dwukolumnowa 'etykieta || wartość' (Zleceniodawca, Rachunek zleceniodawcy, Odbiorca, Rachunek odbiorcy, Kwota, Data operacji, Tytuł przelewu, Numer referencyjny, Status: ZREALIZOWANO)", title="POTWIERDZENIE WYKONANIA PRZELEWU"),
    dict(name="Pomorski Bank Spółdzielczy", nr="CEN", layout="lista linii 'Etykieta: wartość' bez tabeli; etykiety: 'Z rachunku', 'Nazwa nadawcy', 'Na rachunek', 'Nazwa odbiorcy', 'Kwota', 'Data realizacji', 'Tytułem', 'Nr transakcji'", title="Szczegóły operacji"),
    dict(name="NovaBank Polska S.A.", nr="NB", layout="dwie sekcje z nagłówkami '## Dane zleceniodawcy' i '## Dane odbiorcy', potem sekcja '## Szczegóły przelewu' (tabela 2-kolumnowa)", title="Potwierdzenie przelewu krajowego (Elixir)"),
    dict(name="Bank Hanzeatycki S.A.", nr="CEN", layout="dwujęzyczne etykiety polsko-angielskie, np. 'Nadawca / Ordering party', 'Rachunek nadawcy / Debit account', 'Beneficjent / Beneficiary', 'Kwota / Amount', 'Data / Value date', 'Tytuł / Details', 'Ref.'", title="POTWIERDZENIE TRANSAKCJI / TRANSACTION CONFIRMATION"),
    dict(name="Credit Mazovia Bank S.A.", nr="none", layout="krótki tekst ciągły w formie zaświadczenia: 'Bank potwierdza, że w dniu ... z rachunku nr ... prowadzonego dla ... zrealizowano przelew na rachunek nr ... odbiorcy ... w kwocie ... tytułem: ...' oraz pieczątka 'Dokument wygenerowany elektronicznie, nie wymaga podpisu'", title="ZAŚWIADCZENIE O WYKONANIU PRZELEWU"),
    dict(name="Bank Łużycki S.A.", nr="TRX", layout="tabela trzykolumnowa z nagłówkiem 'Pole || Wartość || Uwagi' (w kolumnie Uwagi np. 'IBAN', 'PLN', 'zgodnie z dyspozycją')", title="Potwierdzenie realizacji zlecenia"),
    dict(name="Śląski Bank Rzemiosła", nr="CEN", layout="wyciąg/historia operacji – pojedyncza pozycja w tabeli z kolumnami 'Data księgowania || Opis operacji || Winien || Ma' (kwota w kolumnie Winien, kolumna Ma pusta) oraz pod tabelą szczegóły: rachunek nadawcy, rachunek odbiorcy, nazwa odbiorcy, tytuł, nr referencyjny", title="POTWIERDZENIE OPERACJI – HISTORIA RACHUNKU"),
    dict(name="mBank Spółdzielczy Kujawy", nr="CEN", layout="tabela dwukolumnowa 'Nadawca || Odbiorca' – w kolumnach nazwy, adresy i numery rachunków; pod spodem lista 'Kwota', 'Data operacji', 'Tytuł', 'Identyfikator'", title="Potwierdzenie przelewu"),
]
HARD_BANK = {"winien_ma": 6, "nadawca_odbiorca": 7, "three_col": 5, "narrative": 4, "bilingual": 3}

MON_GEN = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
           "października", "listopada", "grudnia"]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
ORD_GEN = {1: "pierwszego", 2: "drugiego", 3: "trzeciego", 4: "czwartego", 5: "piątego", 6: "szóstego",
           7: "siódmego", 8: "ósmego", 9: "dziewiątego", 10: "dziesiątego", 11: "jedenastego", 12: "dwunastego",
           13: "trzynastego", 14: "czternastego", 15: "piętnastego", 16: "szesnastego", 17: "siedemnastego",
           18: "osiemnastego", 19: "dziewiętnastego", 20: "dwudziestego", 30: "trzydziestego"}
UNITS = ["", "jeden", "dwa", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć",
         "jedenaście", "dwanaście", "trzynaście", "czternaście", "piętnaście", "szesnaście", "siedemnaście",
         "osiemnaście", "dziewiętnaście"]
TENS = ["", "", "dwadzieścia", "trzydzieści", "czterdzieści", "pięćdziesiąt", "sześćdziesiąt", "siedemdziesiąt",
        "osiemdziesiąt", "dziewięćdziesiąt"]
HUNDS = ["", "sto", "dwieście", "trzysta", "czterysta", "pięćset", "sześćset", "siedemset", "osiemset", "dziewięćset"]


def ord_day(d):
    return ORD_GEN.get(d) or f"{ORD_GEN[d // 10 * 10]} {ORD_GEN[d % 10]}"


def _three(n):
    out = [HUNDS[n // 100]]
    r = n % 100
    out += [UNITS[r]] if r < 20 else [TENS[r // 10], UNITS[r % 10]]
    return " ".join(x for x in out if x)


def _form(n, one, few, many):
    if n == 1:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many


def amount_words(n: int) -> str:
    th, rest = divmod(n, 1000)
    parts = []
    if th:
        parts += ["tysiąc"] if th == 1 else [_three(th), _form(th, "tysiąc", "tysiące", "tysięcy")]
    if rest:
        parts.append(_three(rest))
    return " ".join(parts) + " " + _form(n, "złoty", "złote", "złotych")


def fmt_money(v: float, style: str) -> str:
    i = int(round(v))
    sp = f"{i:,}".replace(",", " ")
    dot = f"{i:,}".replace(",", ".")
    return {"pl": f"{sp},00 PLN", "zl": f"{sp},00 zł", "pre": f"PLN {sp},00", "en": f"{i:.2f} PLN",
            "neg": f"-{sp},00 PLN", "dotk": f"{dot},00 zł", "words": (f"{sp},00 PLN (słownie: {amount_words(i)} 00/100)" if style == "words" else ""),
            "dash": f"{sp},- zł", "plain": f"{i} PLN"}[style]


def fmt_date(d: dt.date, style: str) -> str:
    return {"long": f"{d.day} {MON_GEN[d.month - 1]} {d.year} r.", "longnr": f"{d.day} {MON_GEN[d.month - 1]} {d.year}",
            "dots": f"{d.day:02d}.{d.month:02d}.{d.year} r.", "dotsnr": f"{d.day:02d}.{d.month:02d}.{d.year}",
            "iso": d.isoformat(), "roman": f"{d.day} {ROMAN[d.month - 1]} {d.year} r.",
            "words": f"{ord_day(d.day)} {MON_GEN[d.month - 1]} {d.year} roku",
            "roku": f"{d.day} {MON_GEN[d.month - 1]} {d.year} roku", "compact": f"{d.day:02d}.{d.month:02d}.{d.year}r.",
            "slash": f"{d.day:02d}/{d.month:02d}/{d.year}"}[style]


def fem(last):
    for a, b in (("ski", "ska"), ("cki", "cka"), ("dzki", "dzka")):
        if last.endswith(a):
            return last[: -len(a)] + b
    return last


# ============================================================================ identifiers
def nip(rng):
    while True:
        d = [9, 9, 9] + [rng.randint(0, 9) for _ in range(6)]
        c = sum(a * b for a, b in zip(d, [6, 5, 7, 2, 3, 4, 5, 6, 7])) % 11
        if c < 10:
            return "".join(map(str, d + [c]))


def regon(rng):
    d = [9, 9, 9] + [rng.randint(0, 9) for _ in range(5)]
    c = sum(a * b for a, b in zip(d, [8, 9, 2, 3, 4, 5, 6, 7])) % 11 % 10
    return "".join(map(str, d + [c]))


def krs(rng):
    return "999" + "".join(str(rng.randint(0, 9)) for _ in range(7))


def iban(rng):
    bban = "".join(str(rng.randint(0, 9)) for _ in range(24))
    chk = 98 - int(bban + "252100") % 97
    return f"{chk:02d}{bban}"


def fmt_acc(a, style):
    g = " ".join(a[i:i + 4] for i in range(2, 26, 4))
    return {"raw": a, "pl": "PL" + a, "spaced": f"{a[:2]} {g}", "plspaced": f"PL{a[:2]} {g}"}[style]


def pesel(rng, female):
    y, m, d = rng.randint(1964, 1997), rng.randint(1, 12), rng.randint(1, 28)
    mm = m + (20 if y >= 2000 else 0)
    serial = [rng.randint(0, 9) for _ in range(3)]
    sex = rng.choice([0, 2, 4, 6, 8] if female else [1, 3, 5, 7, 9])
    digs = [int(c) for c in f"{y % 100:02d}{mm:02d}{d:02d}"] + serial + [sex]
    c = (10 - sum(a * b for a, b in zip(digs, [1, 3, 7, 9, 1, 3, 7, 9, 1, 3])) % 10) % 10
    return "".join(map(str, digs + [c]))


# ============================================================================ fact generation
class Gen:
    def __init__(self, rng):
        self.rng = rng
        self.used = set()

    def uniq(self, f):
        for _ in range(200):
            v = f()
            if v not in self.used:
                self.used.add(v)
                return v
        raise RuntimeError("pool exhausted")

    def person(self, female=None):
        r = self.rng
        female = r.random() < 0.5 if female is None else female

        def mk():
            last = r.choice(LAST)
            return (r.choice(FIRST_F), fem(last)) if female else (r.choice(FIRST_M), last)
        f, l = self.uniq(mk)
        return {"first": f, "last": l, "name": f"{f} {l}", "female": female}

    def addr(self, city=None):
        r = self.rng
        c, p = city or r.choice(CITIES)
        st = r.choice(STREETS)
        st = st if st.startswith(("al.", "pl.")) else "ul. " + st
        return f"{st} {r.randint(1, 180)}{r.choice(['', '', '', '/' + str(r.randint(1, 40)), 'A'])}, " \
               f"{p}{r.randint(0, 9)}-{r.randint(100, 999)} {c}"

    def company(self):
        r = self.rng

        def mk():
            s = r.choice(STEMS)
            k = r.random()
            if k < 0.5:
                return f"{s} {r.choice(SECTORS)} {r.choice(FORMS)}"
            if k < 0.75:
                return f"{s.upper()}-{r.choice(['BUD', 'TECH', 'MED', 'INVEST', 'TRANS', 'SERWIS', 'ENERGO'])} {r.choice(FORMS)}"
            return f"{s} {r.choice(STEMS)} {r.choice(FORMS)}"
        return {"name": self.uniq(mk), "krs": krs(r), "nip": nip(r), "regon": regon(r), "addr": self.addr()}

    def public_entity(self):
        r = self.rng
        t, tloc = r.choice(TOWNS)
        opts = [(f"Gmina {t}", False), (f"Zakład Gospodarki Komunalnej w {tloc} sp. z o.o.", True),
                (f"Szpital Specjalistyczny im. {r.choice(PATRONS)} w {tloc}", r.random() < 0.5),
                (f"Zarząd Dróg Powiatowych w {tloc}", False),
                (f"Przedsiębiorstwo Wodociągów i Kanalizacji w {tloc} sp. z o.o.", True),
                (f"Centrum Usług Wspólnych w {tloc}", False), (f"Miejskie Przedsiębiorstwo Komunikacyjne w {tloc} S.A.", True),
                (f"Powiatowe Centrum Medyczne w {tloc} sp. z o.o.", True), (f"Miasto i Gmina {t}", False),
                (f"Zespół Szkół Technicznych w {tloc}", False)]
        name, has_krs = self.uniq(lambda: r.choice(opts))
        return {"name": name, "krs": krs(r) if has_krs else None, "nip": nip(r), "regon": regon(r),
                "addr": self.addr((t, r.choice("123456789"))), "town": (t, tloc)}

    def sole_trader(self):
        r = self.rng
        p = self.person()
        firm = r.choice([f"{r.choice(STEMS).upper()}-{r.choice(['INSTAL', 'BUD', 'TECH', 'SERWIS', 'PROJEKT'])} {p['name']}",
                         f"Usługi Remontowo-Budowlane {p['name']}", f"{p['name']} {r.choice(STEMS)} Consulting",
                         f"Przedsiębiorstwo Handlowo-Usługowe {r.choice(STEMS).upper()} {p['name']}"])
        return {"name": firm, "krs": None, "nip": nip(r), "regon": regon(r), "addr": self.addr(), "owner": p}


def nr_postepowania(rng, year):
    a, b = rng.randint(1, 99), rng.randint(1, 400)
    return rng.choice([f"ZP.271.{b}.{year}", f"DZP/PN/{b:03d}/{year}", f"SA.270.2.{a}.{year}", f"ZTI.2110.{a}.{year}",
                       f"IR.272.{a}.{year}", f"ZDP/ZP-{a}/{year}", f"{rng.choice(['WZP', 'DAZ', 'ZOZ'])}-{b}/{year}",
                       f"BZP.IV.261.{a}.{year}", f"PN/{a}/{year}/RB", f"Or.271.{a}.{year}"])


# ============================================================================ difficulties
# Each: key -> dict(docs, desc, excl, ok(case)->bool, apply(case, rng))
def _instr(C, doc, s):
    C["instr"][doc].append(s)


def d_order_labels(C, r):
    C["flags"]["zam_first"] = True
    lab = r.choice([("Wykonawca wnoszący odwołanie:", "Podmiot zamawiający:"),
                    ("ODWOŁUJĄCY (Wykonawca):", "ZAMAWIAJĄCY (Instytucja zamawiająca):"),
                    ("Strona wnosząca odwołanie –", "Strona przeciwna (Zamawiający) –")])
    _instr(C, "odwolanie", f"Blok Zamawiającego umieść PRZED blokiem Odwołującego. Użyj nietypowych etykiet bloków stron: "
                           f"'{lab[1]}' oraz '{lab[0]}'. Sekcję opisującą postępowanie zatytułuj inaczej niż 'dotyczy', np. "
                           f"'Oznaczenie postępowania' lub 'Przedmiot odwołania', a sekcje uzasadnienia numeruj cyframi rzymskimi.")


def d_header_format(C, r):
    st = r.choice(["words", "roman", "iso", "compact", "slash", "roku"])
    C["header"]["fmt"] = st
    if r.random() < 0.5:
        C["header"]["mode"] = "after_parties"
    C["flags"]["header_fmt"] = st


def d_no_header_date(C, r):
    C["header"]["mode"] = "none"


def d_notice_alt(C, r):
    if C["bzp"] is None and C["ted"] is None:
        C["bzp"] = bzp_number(r, C["notice_year"])
    if C["bzp"]:
        if r.random() < 0.4:
            C["bzp"] = C["bzp"] + f"/{r.randint(1, 4):02d}"
        n = C["bzp"].replace("BZP", "BZP ")
        C["bzp_text"] = r.choice([f"ogłoszenie nr {n} z dnia {fmt_date(C['dates']['ogloszenie'], 'long')}",
                                  f"Biuletyn Zamówień Publicznych, nr ogłoszenia: {n}",
                                  f"BZP: {n}"])
    if C["ted"]:
        num, y = C["ted"].split("-")
        C["ted_text"] = r.choice([f"Dz. Urz. UE S: {y}/S {r.randint(100, 250)}-{num}", f"OJ S {y}/S {r.randint(10, 99):03d}-{num}",
                                  f"numer publikacji ogłoszenia w TED: {y}/S {r.randint(100, 250)}-{num}"])
    C["flags"]["notice_alt"] = True


def d_no_notice(C, r):
    C["bzp"] = C["ted"] = None
    C["bzp_text"] = C["ted_text"] = None
    C["flags"]["no_notice"] = True


def d_platform_ids(C, r):
    ocds = f"ocds-148610-{''.join(r.choice('0123456789abcdef') for _ in range(8))}-{''.join(r.choice('0123456789abcdef') for _ in range(4))}"
    C["distract"]["ids"].append(("identyfikator postępowania na platformie e-Zamówienia", ocds))
    C["distract"]["ids"].append(("ID postępowania na platformie zakupowej zamawiającego", str(r.randint(100000, 999999))))
    _instr(C, "odwolanie", "W sekcji opisującej postępowanie, obok numeru referencyjnego (znaku sprawy), podaj również "
                           "identyfikatory platform zakupowych z DANYCH (ocds i ID platformy) – numer referencyjny ma "
                           "pozostać wyraźnie opisany jako znak sprawy/numer referencyjny.")


def d_consortium(C, r):
    if not C["partners"]:
        C["partners"] = [C["G"].company() for _ in range(r.choice([1, 1, 2]))]
    C["leader_pos"] = len(C["partners"])  # leader listed last
    C["flags"]["leader_last"] = True
    _instr(C, "odwolanie", "Odwołujący to konsorcjum. W bloku Odwołującego NAJPIERW wymień partnera/partnerów konsorcjum "
                           "(z pełnymi danymi), a Lidera konsorcjum (pełnomocnika konsorcjum) podaj JAKO OSTATNIEGO, wyraźnie "
                           "oznaczając go jako Lidera.")
    _instr(C, "pelnomocnictwo", "Pełnomocnictwa udzielają wspólnie wszyscy członkowie konsorcjum w kolejności takiej jak "
                                "w GT (mocodawca[0] pierwszy); dla każdego osobny blok podpisu.")


def d_multi_zam(C, r):
    G = C["G"]
    while len(C["zams"]) < r.choice([2, 2, 3]):
        C["zams"].append(G.public_entity())
    if r.random() < 0.65:
        C["prowadzacy"] = r.randrange(1, len(C["zams"]))  # not the first one
        lab = r.choice(["Zamawiający prowadzący postępowanie", "pełnomocnik Zamawiających, prowadzący postępowanie",
                        "Lider zamawiających wspólnie (prowadzący postępowanie)"])
        _instr(C, "odwolanie", f"Zamawiający wspólni (art. 38 Pzp). Wymień zamawiających w kolejności z GT. Zamawiający "
                               f"o indeksie {C['prowadzacy']} (licząc od 0) ma być oznaczony etykietą '{lab}'; pozostali "
                               f"bez takiego oznaczenia (np. 'Zamawiający 1', 'Zamawiający 2').")
    else:
        C["prowadzacy"] = "none"
        _instr(C, "odwolanie", "Zamawiający wspólni (art. 38 Pzp) – wymień wszystkich w kolejności z GT, ale NIE wskazuj, "
                               "który z nich prowadzi postępowanie ani który jest liderem/pełnomocnikiem.")
    C["flags"]["multi_zam"] = {"n": len(C["zams"]), "prowadzacy": C["prowadzacy"]}


def d_sole_trader(C, r):
    C["odw"] = C["G"].sole_trader()
    C["partners"] = []


def d_attorneys_pesel(C, r):
    G = C["G"]
    while len(C["att"]) < r.choice([2, 3]):
        C["att"].append(new_attorney(G, r))
    for a in C["att"]:
        a["pesel"] = pesel(r, a["female"]) if r.random() < 0.85 else None
    if all(a["pesel"] is None for a in C["att"]):
        C["att"][0]["pesel"] = pesel(r, C["att"][0]["female"])
    _instr(C, "pelnomocnictwo", "Przy każdym pełnomocniku, który ma PESEL w GT, podaj jego numer PESEL (np. 'PESEL: ...'); "
                                "pełnomocnikom z pesel null nie podawaj PESEL. Wymień pełnomocników w kolejności z GT.")


def d_declined(C, r):
    C["flags"]["declined"] = True
    _instr(C, "odwolanie", "Pełnomocników wymień w bierniku/narzędniku, np. 'reprezentowany przez r.pr. Annę Kowalską' lub "
                           "'działającego przez pełnomocnika – adwokata Jana ...' – w treści odwołania bez formy mianownika "
                           "(jedynie w bloku podpisu na końcu mianownik jest dopuszczalny).")
    _instr(C, "pelnomocnictwo", "Pełnomocników podaj w celowniku/bierniku ('udziela pełnomocnictwa radcy prawnemu Annie "
                                "Kowalskiej', 'ustanawia pełnomocnikiem adwokata Jana ...'); osoby podpisujące w narzędniku/dopełniaczu "
                                "w treści ('reprezentowana przez Prezesa Zarządu Jana ...'). W blokach podpisów mianownik jest dopuszczalny.")


def d_act_style(C, r):
    st = r.choice(["list", "narrative_p2", "only_zarzuty", "table"])
    C["flags"]["act_style"] = st
    txt = {"list": "Pierwszą zaskarżoną czynność opisz w numerowanej liście czynności i zaniechań (punkt 1), z datą w nawiasie, "
                   "np. '1) ... (zawiadomienie z dnia ...)'; w liście mogą być kolejne czynności (punkt 2, 3).",
           "narrative_p2": "We wstępie NIE podawaj czynności ani jej daty; czynność z datą opisz dopiero w rozbudowanej sekcji "
                           "'Stan faktyczny' (narracja chronologiczna z innymi datami z DANYCH, czynność pierwszego zarzutu jest "
                           "w niej wyraźnie opisana).",
           "only_zarzuty": "Czynność i jej datę podaj WYŁĄCZNIE w treści zarzutu nr 1 (np. 'Zarzut 1: naruszenie art. ... poprzez "
                           "dokonanie w dniu ... czynności ...'); nigdzie wcześniej nie podawaj daty czynności.",
           "table": "Dodaj krótką tabelę chronologii 'Data || Zdarzenie' z kilkoma zdarzeniami z DANYCH (dystraktory) i z "
                    "czynnością pierwszego zarzutu; data czynności ma być w tabeli w formacie podanym w DANYCH."}[st]
    _instr(C, "odwolanie", txt)


def d_no_act_date(C, r):
    C["act_date"] = None
    _instr(C, "odwolanie", "Pierwszą zaskarżoną czynność opisz BEZ JAKIEJKOLWIEK daty (ani daty czynności, ani daty "
                           "zawiadomienia/publikacji/doręczenia). Użyj w tekście innych dat z DANYCH (dystraktory, z ich "
                           "etykietami), ale żadna nie może być datą czynności pierwszego zarzutu.")


def d_amount_notation(C, r):
    C["przelew"]["amount_style"] = r.choice(["neg", "dotk", "words", "dash", "en", "pre"])
    C["flags"]["amount_style"] = C["przelew"]["amount_style"]


def d_bank_layout(C, r):
    k = r.choice(list(HARD_BANK))
    C["przelew"]["bank"] = BANKS[HARD_BANK[k]]
    C["flags"]["bank_layout"] = k


def d_distractors(C, r):
    G = C["G"]
    extra = G.company()
    C["distract"]["entities"].append(("inny wykonawca, który złożył ofertę (przywołaj go w uzasadnieniu)", extra))
    C["distract"]["ids"] += [("wartość szacunkowa zamówienia (netto)", fmt_money(r.randint(300, 9000) * 1000, "zl")),
                             ("wadium", fmt_money(r.randint(5, 90) * 1000, "zl")),
                             ("sygnatura wcześniejszej sprawy przed KIO w tym postępowaniu", f"KIO {r.randint(100, 3999)}/{str(C['year'])[2:]}"),
                             ("rachunek bankowy Zamawiającego do wnoszenia wadium", fmt_acc(iban(r), "plspaced"))]
    C["flags"]["distractors"] = True
    _instr(C, "odwolanie", "Wpleć w tekst wszystkie dystraktory z DANYCH (inny wykonawca z jego KRS/NIP, wartość zamówienia, "
                           "wadium, sygnatura KIO, rachunek wadialny, daty pomocnicze) – naturalnie, w uzasadnieniu i opisie stanu faktycznego.")
    _instr(C, "przelew", "Dodaj dystraktory: 'Saldo po operacji' z kwotą wielokrotnie większą niż kwota przelewu, "
                         f"'Data wygenerowania potwierdzenia: {fmt_date(C['dates']['print'], 'dotsnr')}', 'Prowizja: 0,00 PLN'.")


def d_long(C, r):
    C["flags"]["long"] = True
    _instr(C, "odwolanie", "To ma być DŁUGIE odwołanie: co najmniej 8 stron A4 (ok. 5000 słów). Rozbuduj uzasadnienie "
                           "(stan faktyczny, każdy zarzut w osobnej sekcji z wywodem prawnym, orzecznictwo KIO opisane bez "
                           "sygnatur i dat, wnioski dowodowe). Wszystkie dane stron, postępowania i data nagłówka muszą być na "
                           "pierwszej stronie; czynność pierwszego zarzutu opisz na stronach 1–2.")


def d_letterhead(C, r):
    C["flags"]["letterhead"] = True
    k = C["kanc"]
    k["nip"], k["krs"] = nip(r), (krs(r) if "sp." in k["name"] else None)
    if r.random() < 0.5:
        C["kanc"]["mail_in_footer_only"] = True
    _instr(C, "odwolanie", "Pismo na papierze firmowym kancelarii: pierwsze linie dokumentu to nagłówek kancelarii (nazwa, adres, "
                           "NIP" + (", KRS" if k["krs"] else "") + " kancelarii, telefon"
                           + (", e-mail" if k.get("mail") and not k.get("mail_in_footer_only") else "") + "), oddzielony linią '______'. "
                           + ("Adres e-mail kancelarii podaj WYŁĄCZNIE w stopce na końcu dokumentu (małą czcionką, '~~ '), nie przy danych pełnomocnika. "
                              if k.get("mail") and k.get("mail_in_footer_only") else "")
                           + "Identyfikatory kancelarii nie są identyfikatorami Odwołującego.")


def d_id_format(C, r):
    C["flags"]["id_format"] = True
    _instr(C, "odwolanie", "Zapisuj numery NIP z myślnikami (np. 999-123-45-67) lub z prefiksem 'PL', numery KRS poprzedzaj "
                           "'nr KRS' / 'Rejestr Przedsiębiorców KRS pod nr', a REGON ze spacjami co 3 cyfry. Cyfry muszą być identyczne jak w GT.")
    _instr(C, "pelnomocnictwo", "Numer NIP mocodawcy zapisz z myślnikami (999-123-45-67); cyfry jak w GT.")


def d_parties_table(C, r):
    C["flags"]["parties_table"] = True
    _instr(C, "odwolanie", "Dane stron przedstaw w tabeli dwukolumnowej: pierwszy wiersz 'Odwołujący || Zamawiający' "
                           "(albo odwrotnie), kolejne wiersze to nazwy, adresy, identyfikatory i pełnomocnicy w odpowiednich kolumnach.")


def d_signatories(C, r):
    G = C["G"]
    C["attest"] = {**G.person(), "title": r.choice(["adw.", "r.pr.", "notariusz"])}
    C["flags"]["signatories"] = True
    _instr(C, "pelnomocnictwo", "Mocodawcę reprezentują łącznie dwie osoby (reprezentacja łączna wg KRS) – wymień je z funkcjami "
                                "i podpisami. Na dole dodaj adnotację poświadczenia zgodności kopii z oryginałem podpisaną przez "
                                "osobę z pola 'poświadczający' w DANYCH (to NIE jest osoba podpisująca pełnomocnictwo).")


def d_title_noise(C, r):
    p = C["przelew"]
    p["suffix"] = r.choice([" / sygn. wewn. " + f"{r.randint(10, 99)}/{C['year']}", " – opłata za odwołanie", " zgodnie z art. 1 ust. 1 pkt 2 uopsk"])
    C["flags"]["title_noise"] = True
    _instr(C, "przelew", "Tytuł przelewu jest długi – rozbij jego wyświetlanie na dwie linie w polu tytułu (może być w komórce tabeli), "
                         "ale znaki muszą być identyczne. Dodaj też pole 'Dane dodatkowe' z inną treścią (np. 'Kategoria: opłaty urzędowe').")


DIFFS = {
    "order_labels": dict(f=d_order_labels, docs=["odwolanie"], excl={"parties_table"}),
    "header_format": dict(f=d_header_format, docs=["odwolanie"], excl={"no_header_date"}),
    "no_header_date": dict(f=d_no_header_date, docs=["odwolanie"], excl={"header_format", "letterhead"}),
    "notice_alt": dict(f=d_notice_alt, docs=["odwolanie"], excl={"no_notice"}),
    "no_notice": dict(f=d_no_notice, docs=["odwolanie"], excl={"notice_alt"}),
    "platform_ids": dict(f=d_platform_ids, docs=["odwolanie"], excl=set()),
    "consortium": dict(f=d_consortium, docs=["odwolanie", "pelnomocnictwo"], excl={"sole_trader"}),
    "multi_zam": dict(f=d_multi_zam, docs=["odwolanie"], excl=set()),
    "sole_trader": dict(f=d_sole_trader, docs=["odwolanie", "pelnomocnictwo", "przelew"], excl={"consortium", "signatories"}),
    "attorneys_pesel": dict(f=d_attorneys_pesel, docs=["pelnomocnictwo"], excl=set()),
    "declined_names": dict(f=d_declined, docs=["odwolanie", "pelnomocnictwo"], excl=set()),
    "act_style": dict(f=d_act_style, docs=["odwolanie"], excl={"no_act_date"}),
    "no_act_date": dict(f=d_no_act_date, docs=["odwolanie"], excl={"act_style"}),
    "amount_notation": dict(f=d_amount_notation, docs=["przelew"], excl=set()),
    "bank_layout": dict(f=d_bank_layout, docs=["przelew"], excl=set()),
    "distractors": dict(f=d_distractors, docs=["odwolanie", "przelew"], excl=set()),
    "long_odwolanie": dict(f=d_long, docs=["odwolanie"], excl=set()),
    "letterhead": dict(f=d_letterhead, docs=["odwolanie"], excl={"no_header_date"}),
    "id_format": dict(f=d_id_format, docs=["odwolanie", "pelnomocnictwo"], excl=set()),
    "parties_table": dict(f=d_parties_table, docs=["odwolanie"], excl={"order_labels"}),
    "signatories_attest": dict(f=d_signatories, docs=["pelnomocnictwo"], excl={"sole_trader"}),
    "przelew_title_noise": dict(f=d_title_noise, docs=["przelew"], excl=set()),
}
# order in which difficulties must be applied (structural first)
APPLY_ORDER = ["sole_trader", "consortium", "multi_zam", "attorneys_pesel", "signatories_attest", "no_notice", "notice_alt",
               "platform_ids", "no_header_date", "header_format", "letterhead", "no_act_date", "act_style", "distractors",
               "order_labels", "parties_table", "declined_names", "id_format", "amount_notation", "bank_layout",
               "przelew_title_noise", "long_odwolanie"]
MAX_LONG = 3


# ============================================================================ case construction
def bzp_number(r, year):
    return f"{year}/BZP00999{r.randint(0, 999):03d}"


def new_attorney(G, r):
    p = G.person()
    t = r.choice(["r.pr.", "radca prawny", "adw.", "adwokat", "r. pr."]) if r.random() < 0.9 else \
        ("apl. adw." if r.random() < 0.5 else "aplikant radcowski")
    return {**p, "title": t, "pesel": None}


def kancelaria(G, r, att):
    a = att[0]
    l2 = att[1]["last"] if len(att) > 1 else G.person()["last"]
    solo = f"Kancelaria Adwokacka {a['name']}" if "adw" in a["title"] else f"Kancelaria Radcy Prawnego {a['name']}"
    name = r.choice([solo, f"{a['last']} {l2} i Wspólnicy Kancelaria Prawna sp.k.",
                     solo, f"Kancelaria Prawna {a['last']} i Partnerzy sp.p.",
                     f"{r.choice(STEMS)} Legal {a['last']} sp. k.", f"{a['last']} & {l2} Adwokaci i Radcowie Prawni s.c."])
    asc = a["last"].lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))
    mail = f"{r.choice(['biuro', 'kancelaria', 'sekretariat', 'kontakt', a['first'][0].lower() + '.' + asc])}@{asc}{r.choice(['legal', 'kancelaria', 'prawo', ''])}.example"
    return {"name": name, "addr": G.addr(), "mail": mail, "phone": "000 000 000"}


def build_case(idx: int, source: str, diffs: list[str]) -> dict:
    r = random.Random(f"{SEED}-{idx}")
    G = Gen(r)
    src = {d: json.loads((TRAIN / source / DOCS[d][1]).read_text()) for d in DOCS}
    so, sp = src["odwolanie"], src["pelnomocnictwo"]
    year = 2026
    act = dt.date(year, 1, 1) + dt.timedelta(days=r.randint(25, 345))
    doc_date = act + dt.timedelta(days=r.randint(3, 10))
    pel_date = doc_date - dt.timedelta(days=r.randint(0, 4))
    if pel_date < act:
        pel_date = act
    przelew_date = doc_date - dt.timedelta(days=r.randint(0, 2))
    oglo = act - dt.timedelta(days=r.randint(35, 80))
    dates = {"ogloszenie": oglo, "termin_ofert": act - dt.timedelta(days=r.randint(10, 25)),
             "wezwanie": act - dt.timedelta(days=r.randint(4, 9)), "print": przelew_date + dt.timedelta(days=r.randint(1, 5))}
    dates["wyjasnienia"] = dates["wezwanie"] + dt.timedelta(days=2)
    C = dict(id=f"blind_{idx:02d}", source=source, G=G, year=year, notice_year=oglo.year, flags={}, diffs=diffs,
             instr={d: [] for d in DOCS}, powod=so["OdwolanieKIO"]["czynnosc_powod_id"], act_date=act, doc_date=doc_date,
             pel_date=pel_date, dates=dates, distract={"ids": [], "entities": []}, attest=None)
    C["powod"] = POWOD_OVERRIDE.get(C["id"], C["powod"])
    C["city"] = r.choice(CITIES)[0]
    C["header"] = {"mode": "none" if so["OdwolanieKIO"]["data"] is None else r.choice(["top", "top", "top", "after_parties"]),
                   "fmt": r.choice(["long", "dots", "longnr", "roku", "dotsnr"])}
    # parties (structure inherited from the source case)
    sole = any(m["data"]["typ"] == "osoba_fizyczna" for m in sp["mocodawca"])
    C["odw"] = G.sole_trader() if sole else G.company()
    C["partners"] = [G.company() for _ in range(len(sp["mocodawca"]) - 1)] if not sole else []
    C["leader_pos"] = 0
    C["zams"] = [G.public_entity() if r.random() < 0.8 else G.company() for _ in so["Zamawiajacy"]]
    C["prowadzacy"] = (0 if len(C["zams"]) > 1 else None)
    C["att"] = [new_attorney(G, r) for _ in sp["pelnomocnicy"]]
    for a, s in zip(C["att"], sp["pelnomocnicy"]):
        if s.get("pesel"):
            a["pesel"] = pesel(r, a["female"])
    C["kanc"] = kancelaria(G, r, C["att"])
    C["signers"] = None  # filled after structural difficulties
    # procurement
    C["nr_post"] = nr_postepowania(r, year)
    t, tloc = r.choice(TOWNS)
    t2 = r.choice(TOWNS)[0]
    C["tytul"] = r.choice(TITLES).format(T=t, T2=t2, Tloc=tloc, Tgen=t)
    zp = so["ZamowieniePubliczne"]
    C["bzp"] = bzp_number(r, oglo.year) if zp["numer_bzp"] else None
    C["ted"] = f"999{r.randint(0, 999):03d}-{oglo.year}" if zp["numer_ted"] else None
    C["bzp_text"] = C["bzp"].replace("BZP", "BZP ") if C["bzp"] and r.random() < 0.5 else C["bzp"]
    C["ted_text"] = (C["ted"] if r.random() < 0.6 else f"{oglo.year}/S {r.randint(100, 250)}-{C['ted'].split('-')[0]}") if C["ted"] else None
    # winner / other bidder (natural part of most appeals)
    C["winner"] = G.company()
    # transfer
    bank = r.choice([b for i, b in enumerate(BANKS) if i not in HARD_BANK.values()] + [BANKS[0]])
    wpis = r.random() < 0.3
    kw = r.choice([7500, 15000, 20000]) if wpis else r.choice([17, 34, 51, 100, 200])
    nr = {"CEN": f"CEN{przelew_date:%y%m%d}{r.randint(1000000, 9999999)}", "NB": f"NB/{przelew_date:%Y%m%d}/{r.randint(100000, 999999)}",
          "TRX": f"TRX{r.randint(10 ** 11, 10 ** 12 - 1)}", "none": None}[bank["nr"]]
    C["przelew"] = dict(date=przelew_date, kwota=float(kw), z=iban(r), na=iban(r), nr=nr, tytul=None, bank=bank, suffix="",
                        amount_style=r.choice(["pl", "zl", "pl", "plain"]), acc_style=r.choice(["raw", "pl", "spaced", "plspaced"]),
                        date_style=r.choice(["iso", "dotsnr", "longnr"]), wpis=wpis)
    for k in APPLY_ORDER:
        if k in diffs:
            DIFFS[k]["f"](C, r)
    if wpis:
        rec = ("Urząd Zamówień Publicznych", "ul. Postępu 17A, 02-676 Warszawa")
        tyt = r.choice([f"Wpis od odwołania - {C['nr_post']}", f"WPIS OD ODWOLANIA, ZAMAWIAJACY: {C['zams'][0]['name'].upper()}, {C['nr_post']}",
                        f"wpis od odwołania w postępowaniu {C['nr_post']} - {C['odw']['name']}"])
    else:
        rec = ("Urząd m.st. Warszawy – Centrum Obsługi Podatnika", "ul. Obozowa 57, 01-161 Warszawa")
        names = " i ".join(a["name"] for a in C["att"])
        tyt = r.choice([f"opłata skarbowa od pełnomocnictwa dla {names} w postępowaniu przed KIO w przetargu {C['nr_post']}" + (f" {nr}" if nr else ""),
                        f"Oplata skarbowa - pelnomocnictwo KIO - {C['nr_post']}",
                        f"OPŁATA SKARBOWA PEŁNOMOCNICTWO {C['att'][0]['last'].upper()} {C['nr_post']}"])
    C["przelew"].update(tytul=tyt + C["przelew"]["suffix"], recipient=rec)
    members = C["partners"][:C["leader_pos"]] + [C["odw"]] + C["partners"][C["leader_pos"]:]
    C["members"] = members
    if C["signers"] is None:
        C["signers"] = [[{**(m["owner"] if m.get("owner") else G.person()), "fn": "właściciel" if m.get("owner") else r.choice(FUNCTIONS)}]
                        for m in members]
    if "signatories_attest" in diffs:  # signers created after structure: add second signer now
        for i, m in enumerate(members):
            if len(C["signers"][i]) < 2 and not m.get("owner"):
                C["signers"][i].append({**G.person(), "fn": r.choice(FUNCTIONS[1:4])})
    if C["header"]["mode"] == "none":
        C["header_line"] = None
    else:
        C["header_line"] = f"{C['city']}, " + ("dnia " if C["header"]["fmt"] in ("words", "dots", "roku") and r.random() < 0.7 else "") \
                           + fmt_date(doc_date, C["header"]["fmt"])
    C["act_fmt"] = r.choice(["long", "dots", "roku", "dotsnr"])
    C["distract"]["dates"] = {"data publikacji ogłoszenia o zamówieniu": oglo, "termin składania ofert": dates["termin_ofert"],
                              "wezwanie do wyjaśnień (pismo Zamawiającego)": dates["wezwanie"],
                              "złożenie wyjaśnień przez wykonawcę": dates["wyjasnienia"]}
    if C["powod"] in (4, 5, 6, 11, 12) and C["act_date"] is None:
        C["distract"]["dates"].pop("data publikacji ogłoszenia o zamówieniu")
    return C


def build_gt(C) -> dict:
    o = C["odw"]
    a0 = C["att"][0]
    mail = C["kanc"]["mail"]
    odw = {"OdwolanieKIO": {"data": C["doc_date"].isoformat() if C["header_line"] else None,
                            "czynnosc_dzien": C["act_date"].isoformat() if C["act_date"] else None,
                            "czynnosc_powod_id": C["powod"], "czynnosc_opis": POWOD[C["powod"]],
                            "miejscowosc": C["city"] if C["header_line"] else None},
           "Odwolujacy": [{"krs": o["krs"], "nazwa": o["name"], "nip": o["nip"], "regon": o["regon"], "przez-pelnomocnika": 1,
                           "pelnomocnik": {"imie_nazwisko": a0["name"], "nazwa": C["kanc"]["name"], "mail": mail}}],
           "Zamawiajacy": [], "ZamowieniePubliczne": {"numer_bzp": C["bzp"], "numer_postepowania": C["nr_post"],
                                                      "numer_ted": C["ted"], "tytul": C["tytul"]}}
    for i, z in enumerate(C["zams"]):
        pp = None
        if len(C["zams"]) > 1:
            pp = 0 if C["prowadzacy"] == "none" else int(i == C["prowadzacy"])
        odw["Zamawiajacy"].append({"krs": z["krs"], "nazwa": z["name"], "nip": z["nip"], "regon": z["regon"],
                                   "prowadzacy_postepowanie": pp})
    pel = {"mocodawca": [], "pelnomocnicy": [{"imie_nazwisko": a["name"], "pesel": a["pesel"]} for a in C["att"]]}
    for m, sg in zip(C["members"], C["signers"]):
        own = m.get("owner")
        pel["mocodawca"].append({"data": {"imie_nazwisko": own["name"] if own else None, "krs": m["krs"], "nazwa": m["name"],
                                          "nip": m["nip"], "typ": "osoba_fizyczna" if own else "osoba_prawna"},
                                 "podpisujacy": [{"imie_nazwisko": s["name"]} for s in sg]})
    p = C["przelew"]
    prz = {"przelew_bankowy": {"data_operacji": p["date"].isoformat(), "kwota": p["kwota"], "na_rachunek": p["na"],
                               "numer_transakcji": p["nr"], "tytul": p["tytul"], "z_rachunku": p["z"]}}
    return {"odwolanie": odw, "pelnomocnictwo": pel, "przelew": prz}


# ============================================================================ prompts
POWOD_SEM = {
    1: "odrzucenie oferty ODWOŁUJĄCEGO (zawiadomienie o odrzuceniu jego oferty)",
    2: "wybór jako najkorzystniejszej oferty INNEGO wykonawcy (zarzut nr 1 kwestionuje samą czynność wyboru/oceny ofert, nie zaniechanie odrzucenia czy wykluczenia)",
    3: "wykluczenie ODWOŁUJĄCEGO z postępowania",
    4: "postanowienia SWZ opublikowanej wraz z ogłoszeniem o zamówieniu (np. warunki udziału, kryteria oceny ofert, projektowane postanowienia umowy) – NIE opis przedmiotu zamówienia i NIE zmiana SWZ",
    5: "zmiana (modyfikacja) treści SWZ dokonana przez Zamawiającego",
    6: "odpowiedzi Zamawiającego na pytania wykonawców / wyjaśnienia treści SWZ",
    7: "zaniechanie odrzucenia oferty INNEGO wykonawcy",
    8: "zaniechanie wykluczenia INNEGO wykonawcy z postępowania",
    9: "unieważnienie postępowania przez Zamawiającego",
    10: "zaniechanie unieważnienia postępowania (Odwołujący żąda unieważnienia postępowania)",
    11: "opis przedmiotu zamówienia (OPZ) – wymagania techniczne/funkcjonalne naruszające uczciwą konkurencję (nie warunki udziału, nie kryteria)",
    12: "projektowane postanowienia umowy (wzór umowy – załącznik do SWZ), np. nadmierne kary umowne, brak waloryzacji wynagrodzenia, "
        "nierównomierny rozkład ryzyk – zarzut nr 1 dotyczy WYŁĄCZNIE postanowień wzoru umowy, nie warunków udziału, nie OPZ",
}
STYLES = ["formalny i zwięzły, sekcje numerowane I., II., III.; 'Działając w imieniu i na rzecz…'",
          "rozbudowany, akademicki, z sekcjami A., B., C. i podsekcjami; długie zdania",
          "nowoczesny: pogrubione nagłówki '## ', krótkie akapity, listy punktowane",
          "tradycyjny kancelaryjny: 'Imieniem Odwołującego wnoszę…', paragrafy numerowane §",
          "rzeczowy, w stylu dużej kancelarii: 'ODWOŁANIE' + podtytuł 'od czynności i zaniechań Zamawiającego', numeracja 1., 1.1., 1.2."]
MARKUP = """FORMAT WYJŚCIA (prosty markup, jedna linia = jeden akapit/wiersz):
'# TEKST' wyśrodkowany pogrubiony tytuł | '## TEKST' pogrubiony nagłówek do lewej | '>> TEKST' linia do prawej
'A || B' wiersz tabeli (kolejne takie linie = jedna tabela; 3 kolumny: 'A || B || C') | '~~ TEKST' mała szara czcionka (stopka/uwagi)
'---' podział strony | pusta linia = odstęp | inne linie = zwykły akapit (NIE łam zdań ręcznie).
Zwróć WYŁĄCZNIE treść dokumentu w tym formacie, bez komentarzy i bez bloków kodu."""

PROMPT = """Jesteś generatorem realistycznych polskich dokumentów (pisma procesowe w zamówieniach publicznych, dokumenty bankowe) do testu systemu ekstrakcji danych.
Napisz OD NOWA dokument: {kind}.
Dokument ma wyglądać jak prawdziwy dokument innej kancelarii/banku niż wzór – własny układ, własne sformułowania.

ŻELAZNE ZASADY:
1. Każda niepusta wartość z DOCELOWEGO JSON-a (ground truth) musi jednoznacznie wynikać z dokumentu: nazwy podmiotów znak w znak,
   identyfikatory (KRS/NIP/REGON/PESEL/rachunki) z identycznymi cyframi, daty i kwoty zgodne (formaty zapisu – patrz WYMAGANE ZAPISY).
2. Wartości null w GT NIE mogą występować w dokumencie (np. mail null = brak e-maila pełnomocnika; pesel null = brak PESEL;
   numer_ted null = brak numeru TED / Dz.Urz.UE; numer_bzp null = brak numeru BZP).
3. NIE wymyślaj żadnych innych identyfikatorów (NIP/KRS/REGON/PESEL/rachunków/sygnatur/numerów ogłoszeń), dat, kwot, podmiotów ani osób
   poza tymi z DANYCH i GT. Telefon tylko '000 000 000'. Daty ustawy Pzp ('ustawa z dnia 11 września 2019 r.') i publikatory Dz.U. są dozwolone.
4. Każdy łańcuch z sekcji WYMAGANE ZAPISY ma się pojawić w dokumencie DOKŁADNIE (dosłownie, znak w znak).
5. NIE cytuj kanonicznych etykiet z JSON-a ani nazw pól – pisz naturalnym językiem.
6. Wzór gatunkowy służy tylko jako przykład gatunku – nie kopiuj z niego nazw, osób, numerów, dat ani całych zdań.
{extra_rules}
DANE SPRAWY:
{facts}

WYMAGANE ZAPISY (dosłownie):
{required}

UKŁAD, STYL I TRUDNOŚCI (obowiązkowe):
{instr}

DOCELOWY JSON (ground truth):
{gt}

WZÓR GATUNKOWY (inna sprawa – tylko do inspiracji gatunkiem):
{example}

{markup}"""


def ent_line(e, label=""):
    ids = ", ".join(f"{k.upper()}: {e[k]}" for k in ("krs", "nip", "regon") if e.get(k))
    return f"{label}{e['name']}, {e['addr']}" + (f", {ids}" if ids else "")


def ascii_slug(name):
    words = [w for w in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{4,}", name)]
    w = words[-1] if words else "zamawiajacy"
    return w.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


def name_present(name, text):
    """Lenient: first- and last-name stems present (declined forms allowed)."""
    f, *rest = name.split()
    l = rest[-1] if rest else f
    stem = lambda w: w[: max(3, len(w) - 2)].lower()
    t = text.lower()
    return stem(f) in t and stem(l) in t


def facts_odwolanie(C, gt):
    L = []
    for i, m in enumerate(C["members"]):
        role = "Odwołujący" if len(C["members"]) == 1 else ("LIDER konsorcjum" if m is C["odw"] else "Partner konsorcjum")
        L.append(ent_line(m, f"- {role}: ") + (f" (przedsiębiorca – osoba fizyczna {m['owner']['name']}, CEIDG)" if m.get("owner") else ""))
    for i, z in enumerate(C["zams"]):
        L.append(ent_line(z, f"- Zamawiający [{i}]: ") + f", e-mail: zamowienia@{ascii_slug(z['name'])}.example")
    L.append("- Pełnomocnicy Odwołującego (kolejność obowiązkowa): " + "; ".join(f"{a['title']} {a['name']}" for a in C["att"]))
    k = C["kanc"]
    L.append(f"- Kancelaria: {k['name']}, {k['addr']}, tel. {k['phone']}" + (f", e-mail: {k['mail']}" if k.get("mail") else ", (brak e-maila)")
             + (f", NIP kancelarii: {k['nip']}" if k.get("nip") else "") + (f", KRS kancelarii: {k['krs']}" if k.get("krs") else ""))
    w = C["winner"]
    L.append(ent_line(w, f"- Inny wykonawca ({'którego dotyczy czynność' if C['powod'] in (2, 7, 8) else 'konkurent w postępowaniu'}): "))
    for lab, e in C["distract"]["entities"]:
        L.append(ent_line(e, f"- {lab}: "))
    L.append(f"- Tytuł zamówienia: {C['tytul']}")
    L.append(f"- Numer referencyjny / znak sprawy: {C['nr_post']}")
    if C["bzp"]:
        L.append(f"- Ogłoszenie w BZP: {C['bzp_text']}")
    if C["ted"]:
        L.append(f"- Ogłoszenie w Dz.Urz.UE (TED): {C['ted_text']}")
    L.append(f"- Pierwszy zarzut / pierwsza zaskarżona czynność: {POWOD_SEM[C['powod']]}"
             + (f" – dotyczy wykonawcy {w['name']}" if C["powod"] in (2, 7, 8) else ""))
    if C["act_date"]:
        L.append(f"- Data tej czynności: {fmt_date(C['act_date'], C['act_fmt'])}")
    else:
        L.append("- Data tej czynności: BRAK – nie podawaj żadnej daty dla tej czynności")
    L.append("- Kolejne zarzuty (2., 3.) mogą dotyczyć innych czynności; daty pomocnicze (dystraktory):")
    for lab, d in C["distract"]["dates"].items():
        L.append(f"    * {lab}: {fmt_date(d, C['act_fmt'])}")
    for lab, v in C["distract"]["ids"]:
        L.append(f"- {lab}: {v}")
    if C["header_line"]:
        pos = {"top": "w prawym górnym rogu na samej górze pierwszej strony ('>> ')",
               "after_parties": "NIE na górze strony: dopiero pod blokami stron / sekcją dotyczy, tuż przed tytułem lub wstępem (linia '>> ')"}[C["header"]["mode"]]
        L.append(f"- Linia miejscowości i daty sporządzenia: '{C['header_line']}' – umieść {pos}; nie powtarzaj jej nigdzie indziej.")
    else:
        L.append("- Odwołanie NIE zawiera linii miejscowości i daty sporządzenia (nigdzie, także przy podpisie).")
    return "\n".join(L)


def facts_pel(C, gt):
    L = []
    for m, sg in zip(C["members"], C["signers"]):
        L.append(ent_line({k: v for k, v in m.items() if k != "regon"} | {"regon": m["regon"]}, "- Mocodawca: ")
                 + (f" (osoba fizyczna prowadząca działalność: {m['owner']['name']}, CEIDG)" if m.get("owner") else ""))
        L.append("    podpisujący: " + "; ".join(f"{s['name']} – {s['fn']}" for s in sg))
    L.append("- Pełnomocnicy (kolejność obowiązkowa): " + "; ".join(
        f"{a['title']} {a['name']}" + (f", PESEL {a['pesel']}" if a["pesel"] else "") for a in C["att"]))
    L.append(f"- Postępowanie: „{C['tytul']}”, nr {C['nr_post']}, prowadzone przez {C['zams'][0]['name']}")
    L.append(f"- Miejscowość i data pełnomocnictwa: {re.search(r'\d{2}-\d{3} (.+)$', C['odw']['addr']).group(1)}, {fmt_date(C['pel_date'], random.Random(C['id']).choice(['long', 'dotsnr', 'longnr']))}")
    if C["attest"]:
        a = C["attest"]
        L.append(f"- poświadczający zgodność kopii z oryginałem: {a['title']} {a['name']}")
    return "\n".join(L)


def facts_przelew(C, gt):
    p = C["przelew"]
    b = p["bank"]
    payer = C["odw"]
    L = [f"- Bank: {b['name']}; tytuł dokumentu: {b['title']}",
         f"- Układ: {b['layout']}",
         f"- Zleceniodawca (nadawca): {payer['name']}, {payer['addr']}",
         f"- Rachunek zleceniodawcy: {fmt_acc(p['z'], p['acc_style'])}",
         f"- Odbiorca: {p['recipient'][0]}, {p['recipient'][1]}",
         f"- Rachunek odbiorcy: {fmt_acc(p['na'], p['acc_style'])}",
         f"- Kwota: {fmt_money(p['kwota'], p['amount_style'])}",
         f"- Data operacji: {fmt_date(p['date'], p['date_style'])}",
         f"- Tytuł przelewu (znak w znak): {p['tytul']}",
         f"- Numer transakcji/referencyjny: {p['nr'] or 'BRAK – nie podawaj żadnego numeru transakcji/referencji'}"]
    return "\n".join(L)


def required_strings(C, doc) -> list[str]:
    gt = C["gt"][doc]
    req = []
    if doc == "odwolanie":
        o = gt["Odwolujacy"][0]
        req += [o["nazwa"], C["tytul"], C["nr_post"]] + [z["nazwa"] for z in gt["Zamawiajacy"]]
        req += [o["pelnomocnik"]["nazwa"]] + ([o["pelnomocnik"]["mail"]] if o["pelnomocnik"]["mail"] else [])
        if C["header_line"]:
            req.append(C["header_line"])
        if C["bzp"]:
            req.append(C["bzp_text"])
        if C["ted"]:
            req.append(C["ted_text"])
        if C["act_date"]:
            req.append(fmt_date(C["act_date"], C["act_fmt"]))
        for m in C["members"]:
            req.append(m["name"])

    elif doc == "pelnomocnictwo":
        req += [m["data"]["nazwa"] for m in gt["mocodawca"]]
        req += [a["pesel"] for a in gt["pelnomocnicy"] if a["pesel"]]
    else:
        p = C["przelew"]
        req += [p["tytul"], fmt_money(p["kwota"], p["amount_style"]), fmt_date(p["date"], p["date_style"]),
                fmt_acc(p["z"], p["acc_style"]), fmt_acc(p["na"], p["acc_style"])] + ([p["nr"]] if p["nr"] else [])
    return req


def doc_instr(C, doc, r):
    base = []
    if doc == "odwolanie":
        base.append(f"Styl kancelarii: {r.choice(STYLES)}.")
        base.append(r.choice(["Adresat: 'Prezes Krajowej Izby Odwoławczej, ul. Postępu 17A, 02-676 Warszawa'.",
                              "Adresat: 'Krajowa Izba Odwoławcza przy Prezesie Urzędu Zamówień Publicznych, ul. Postępu 17A, 02-676 Warszawa'.",
                              "Adresat: 'Do Prezesa Krajowej Izby Odwoławczej' (bez adresu)."]))
        if not C["flags"].get("long"):
            base.append(f"Długość: {r.choice(['2–3', '3–4', '3'])} strony A4 (zarzuty + uzasadnienie + wnioski + załączniki).")
        base.append("Pełnomocnik Odwołującego wymieniony jako pierwszy to pierwsza osoba z listy pełnomocników; zachowaj kolejność.")
        if len(C["zams"]) > 1 and "multi_zam" not in C["diffs"]:
            base.append("Zamawiający wspólni – pierwszy z GT oznaczony jako 'Zamawiający – Lider, prowadzący postępowanie', kolejny jako 'Partner'.")
        if len(C["members"]) > 1 and not C["flags"].get("leader_last"):
            base.append("Odwołujący to konsorcjum: najpierw Lider (oznaczony jako Lider), potem partner(zy).")
        if C["kanc"].get("mail") is None:
            base.append("Nie podawaj żadnego adresu e-mail pełnomocnika ani kancelarii.")
    elif doc == "pelnomocnictwo":
        base.append(r.choice(["Struktura paragrafowa § 1, § 2, …", "Jeden-dwa akapity ciągłego tekstu i lista umocowań.",
                              "Nagłówek 'PEŁNOMOCNICTWO PROCESOWE', treść w punktach 1–5.",
                              "Forma 'Ja, niżej podpisany…' / 'My, niżej podpisani…' z listą umocowań."]))
        base.append("Długość: 1 strona. Wymień pełnomocników w kolejności z GT.")
    else:
        base.append("Długość: pół strony – 1 strona. Bez komentarzy. Status operacji: zrealizowana.")
        if C["przelew"]["amount_style"] == "neg":
            base.append("Kwotę pokaż ze znakiem minus (obciążenie rachunku), dokładnie jak w DANYCH.")
    return base + C["instr"][doc]


# ============================================================================ LLM
COST = {"usd": 0.0, "calls": 0}
_LOCK = threading.Lock()


def llm_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT / ".env")
    return OpenAI(base_url=os.environ.get("O2J_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
                  api_key=os.environ["O2J_LLM_API_KEY"], timeout=900)


def generate(client, prompt, max_tokens=12000) -> str:
    last = None
    for _ in range(3):
        try:
            r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.7,
                                               max_tokens=max_tokens,
                                               extra_body={"reasoning": {"effort": "low"}, "usage": {"include": True}})
            u = r.usage.model_dump() if r.usage else {}
            with _LOCK:
                COST["usd"] += float(u.get("cost") or 0)
                COST["calls"] += 1
            s = (r.choices[0].message.content or "").strip()
            s = re.sub(r"^<think>.*?</think>", "", s, flags=re.S).strip()
            s = re.sub(r"^```\w*\n|\n```$", "", s).strip()
            if len(s) > 200:
                return s
            last = RuntimeError(f"short output: {s[:200]!r}")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


# ============================================================================ render
FONTS = {"Arial": ("Arial.ttf", "Arial Bold.ttf"), "Times": ("Times New Roman.ttf", "Times New Roman Bold.ttf"),
         "Georgia": ("Georgia.ttf", "Georgia Bold.ttf"), "Verdana": ("Verdana.ttf", "Verdana Bold.ttf"),
         "Tahoma": ("Tahoma.ttf", "Tahoma Bold.ttf"), "Trebuchet": ("Trebuchet MS.ttf", "Trebuchet MS Bold.ttf"),
         "Courier": ("Courier New.ttf", "Courier New Bold.ttf")}


def render(markup: str, out: Path, style: dict):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fam = style["font"]
    reg, bold = f"B-{fam}", f"B-{fam}-Bold"
    if reg not in pdfmetrics.getRegisteredFontNames():
        sup = "/System/Library/Fonts/Supplemental/"
        pdfmetrics.registerFont(TTFont(reg, sup + FONTS[fam][0]))
        pdfmetrics.registerFont(TTFont(bold, sup + FONTS[fam][1]))
    fs = style["size"]
    body = ParagraphStyle("b", fontName=reg, fontSize=fs, leading=fs * 1.32,
                          alignment=TA_JUSTIFY if style["justify"] else TA_LEFT, spaceAfter=fs * 0.25)
    right = ParagraphStyle("r", parent=body, alignment=TA_RIGHT)
    head = ParagraphStyle("h", parent=body, fontName=bold, alignment=TA_LEFT, spaceBefore=fs * 0.5)
    title = ParagraphStyle("t", parent=body, fontName=bold, fontSize=fs + 4, leading=(fs + 4) * 1.3, alignment=TA_CENTER,
                           spaceBefore=6, spaceAfter=6)
    small = ParagraphStyle("s", parent=body, fontSize=fs - 2.5, leading=(fs - 2.5) * 1.3, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("c", parent=body, fontSize=fs - 0.5, leading=(fs - 0.5) * 1.25, alignment=TA_LEFT)
    story, table = [], []
    W = A4[0] - 2 * style["margin"] * cm

    def flush():
        if table:
            ncol = max(len(r) for r in table)
            rows = [[Paragraph(escape(c.strip()), cell) for c in r] + [""] * (ncol - len(r)) for r in table]
            t = Table(rows, colWidths=[W / ncol] * ncol)
            ts = [("VALIGN", (0, 0), (-1, -1), "TOP")]
            if style["grid"]:
                ts.append(("GRID", (0, 0), (-1, -1), 0.3, colors.grey))
            else:
                ts.append(("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black))
            t.setStyle(TableStyle(ts))
            story.append(t)
            story.append(Spacer(1, 6))
            table.clear()

    for line in markup.splitlines():
        s = line.rstrip()
        if "||" in s:
            table.append(s.split("||"))
            continue
        flush()
        st = s.strip()
        if not st:
            story.append(Spacer(1, fs * 0.5))
        elif st == "---":
            story.append(PageBreak())
        elif st.startswith("## "):
            story.append(Paragraph(escape(st[3:]), head))
        elif st.startswith("# "):
            story.append(Paragraph(escape(st[2:]), title))
        elif st.startswith(">>"):
            story.append(Paragraph(escape(st[2:].strip()), right))
        elif st.startswith("~~"):
            story.append(Paragraph(escape(st[2:].strip()), small))
        else:
            story.append(Paragraph(escape(st), body))
    flush()

    def page_deco(canvas, doc):
        if style.get("pageno"):
            canvas.saveState()
            canvas.setFont(reg, fs - 2)
            canvas.drawCentredString(A4[0] / 2, 1.1 * cm, style["pageno"].format(n=doc.page))
            canvas.restoreState()

    out.parent.mkdir(parents=True, exist_ok=True)
    m = style["margin"] * cm
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=m, rightMargin=m, topMargin=m, bottomMargin=m).build(
        story, onFirstPage=page_deco, onLaterPages=page_deco)


def render_style(C, doc, r):
    if doc == "przelew":
        font = "Courier" if C["przelew"]["bank"]["name"].startswith("Śląski") else r.choice(["Arial", "Verdana", "Tahoma", "Trebuchet"])
        return dict(font=font, size=r.choice([9, 9.5, 10]), justify=False, margin=r.choice([1.5, 2.0]), grid=r.random() < 0.5, pageno=None)
    return dict(font=r.choice(["Arial", "Times", "Georgia", "Verdana", "Tahoma", "Trebuchet"]),
                size=r.choice([9.5, 10, 10.5, 11, 11.5]) if doc == "odwolanie" else r.choice([10, 10.5, 11]),
                justify=r.random() < 0.6, margin=r.choice([1.8, 2.0, 2.5]), grid=r.random() < 0.5,
                pageno=r.choice([None, "Strona {n}", "- {n} -", "str. {n}"]) if doc == "odwolanie" else None)


# ============================================================================ checks
DATE_NUM = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})")
DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_TXT = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MON_GEN) + r")\s+(\d{4})", re.I)
DATE_ROM = re.compile(r"\b(\d{1,2})\s+(" + "|".join(ROMAN[::-1]) + r")\s+(\d{4})\b")


def strip_markup(s: str) -> str:
    out = []
    for line in s.splitlines():
        line = re.sub(r"^(##?|>>|~~)\s*", "", line.strip())
        out.append(line.replace("||", " | "))
    return "\n".join(out)


def norm(s):
    return " ".join(s.split()).lower()


def found_dates(text):
    res = set()
    for d, m, y in DATE_NUM.findall(text):
        res.add((int(y), int(m), int(d)))
    for y, m, d in DATE_ISO.findall(text):
        res.add((int(y), int(m), int(d)))
    for d, m, y in DATE_TXT.findall(text):
        res.add((int(y), MON_GEN.index(m.lower()) + 1, int(d)))
    for d, m, y in DATE_ROM.findall(text):
        res.add((int(y), ROMAN.index(m) + 1, int(d)))
    return res


def allowed_numbers(C):
    nums = set()

    def add(x):
        if x:
            nums.add(re.sub(r"\D", "", str(x)))
    for e in C["members"] + C["zams"] + [C["winner"]] + [e for _, e in C["distract"]["entities"]]:
        for k in ("krs", "nip", "regon"):
            add(e.get(k))
    for a in C["att"]:
        add(a["pesel"])
    for k in ("nip", "krs"):
        add(C["kanc"].get(k))
    p = C["przelew"]
    for x in (p["z"], p["na"], p["nr"]):
        add(x)
    for _, v in C["distract"]["ids"]:
        add(v)
    add(C["bzp"])
    add(C["ted"])
    add(C["ted_text"])
    return nums


def run_checks(C, doc, markup) -> tuple[list[str], list[str]]:
    """-> (errors, notes). errors trigger regeneration; notes are for manual review."""
    text = strip_markup(markup)
    nt = norm(text)
    errs, notes = [], []
    for s in required_strings(C, doc):
        if norm(s) not in nt:
            errs.append(f"brak wymaganego zapisu: {s!r}")
    gt = C["gt"][doc]
    names = [a["name"] for a in C["att"]] if doc != "przelew" else []
    if doc == "pelnomocnictwo":
        names += [s["name"] for sg in C["signers"] for s in sg]
    for n in names:
        if not name_present(n, text):
            errs.append(f"brak osoby (w żadnej formie): {n!r}")
    miss = gt_check(gt, text)
    for m in miss:
        path = m.split("=")[0]
        if "imie_nazwisko" in path or "data_operacji" in path or "czynnosc_dzien" in path \
                or ".data=" in m or path.endswith("numer_bzp") or path.endswith("numer_ted") or path.endswith("OdwolanieKIO.data"):
            notes.append("gt_check (oczekiwane – inny format): " + m)
        else:
            errs.append("gt_check: " + m)
    # foreign long numbers
    allowed = allowed_numbers(C)
    for m in re.finditer(r"(?<![\d])(?:PL)?\d[\d \-]{7,}\d(?![\d])", text):
        dig = re.sub(r"\D", "", m.group())
        if len(dig) >= 9 and not any(dig in a or a in dig for a in allowed) and not re.fullmatch(r"0+", dig):
            errs.append(f"obcy numer: {m.group()!r}")
    # dates
    ok = {(d.year, d.month, d.day) for d in [C["doc_date"], C["pel_date"], C["przelew"]["date"], C["dates"]["print"]]
          + list(C["distract"]["dates"].values()) + list(C["dates"].values())}
    if C["act_date"]:
        ok.add((C["act_date"].year, C["act_date"].month, C["act_date"].day))
    ok |= {(2019, 9, 11), (2006, 11, 16), (1964, 4, 23), (1964, 11, 17), (1982, 5, 26), (1982, 7, 6), (2020, 12, 30),
           (1997, 8, 29), (1993, 4, 16), (2020, 12, 31)}
    for d in found_dates(text):
        if d not in ok:
            errs.append(f"obca data: {d}")
    if doc == "odwolanie":
        if not C["act_date"]:
            for d in found_dates(text):
                if d == (C["dates"]["ogloszenie"].year, C["dates"]["ogloszenie"].month, C["dates"]["ogloszenie"].day) and C["powod"] in (4, 11, 12):
                    notes.append("data ogłoszenia obecna przy braku daty czynności – sprawdź ręcznie")
        if C["header_line"] is None and C["doc_date"] and (C["doc_date"].year, C["doc_date"].month, C["doc_date"].day) in found_dates(text):
            errs.append("data sporządzenia obecna mimo braku nagłówka")
        if C["kanc"].get("mail") is None and "@" in text:
            notes.append("w tekście jest '@' (sprawdź, czy nie e-mail pełnomocnika)")
        if C["ted"] is None and re.search(r"\b\d{4}/S\s?\d{1,3}|\bTED\b|Dz\.?\s?Urz\.?\s?UE", text):
            errs.append("ślad numeru TED mimo null")
        if C["bzp"] is None and re.search(r"BZP\s?\d", text):
            errs.append("numer BZP mimo null")
    if doc == "przelew" and C["przelew"]["nr"] is None and re.search(r"(?i)nr ref|referenc|nr transakcji|identyfikator", text):
        notes.append("etykieta numeru transakcji mimo null – sprawdź")
    # leakage of source-case names
    src = {d: json.loads((TRAIN / C["source"] / DOCS[d][1]).read_text()) for d in DOCS}
    for _, v in _leaves_all(src):
        if isinstance(v, str) and len(v) > 8 and not re.fullmatch(r"[\d\-/A-Z.]+", v) and norm(v) in nt and v not in POWOD.values():
            errs.append(f"przeciek z przypadku źródłowego: {v!r}")
    return errs, notes


def _leaves_all(x, p=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves_all(v, f"{p}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves_all(v, f"{p}[{i}]")
    else:
        yield p, x


# ============================================================================ planning
def plan_cases():
    r = random.Random(SEED)
    unused = [f"przyklad_{i:02d}" for i in range(1, 61) if i not in USED_BY_VARIANTS]
    sources = r.sample(unused, N_CASES)
    usage = {k: 0 for k in DIFFS}
    plans = []
    for i, src in enumerate(sources, 1):
        so = json.loads((TRAIN / src / "odwolanie.json").read_text())
        sp = json.loads((TRAIN / src / "pelnomocnictwo.json").read_text())
        k = r.choice([1, 2, 2, 3, 3, 3])
        chosen = []
        for _ in range(k):
            cand = [d for d in DIFFS if d not in chosen and not any(d in DIFFS[c]["excl"] or c in DIFFS[d]["excl"] for c in chosen)]
            if so["OdwolanieKIO"]["data"] is None:
                cand = [d for d in cand if d not in ("header_format", "letterhead", "no_header_date")]
            if any(m["data"]["typ"] == "osoba_fizyczna" for m in sp["mocodawca"]) or len(sp["mocodawca"]) > 1:
                cand = [d for d in cand if d not in ("sole_trader",)]
            if usage["long_odwolanie"] >= MAX_LONG:
                cand = [d for d in cand if d != "long_odwolanie"]
            lo = min(usage[d] for d in cand)
            d = r.choice([d for d in cand if usage[d] == lo])  # coverage-balanced random draw
            chosen.append(d)
            usage[d] += 1
        plans.append((i, src, sorted(chosen, key=APPLY_ORDER.index)))
    return plans


# ============================================================================ main
def inherited(C, src):
    so = json.loads((TRAIN / src / "odwolanie.json").read_text())
    sp = json.loads((TRAIN / src / "pelnomocnictwo.json").read_text())
    tags = []
    if len(sp["mocodawca"]) > 1:
        tags.append("consortium (leader first)")
    if len(so["Zamawiajacy"]) > 1:
        tags.append("multi_zamawiajacy (prowadzący labelled first)")
    if any(m["data"]["typ"] == "osoba_fizyczna" for m in sp["mocodawca"]):
        tags.append("sole_trader")
    if any(p.get("pesel") for p in sp["pelnomocnicy"]):
        tags.append("pesel")
    if so["OdwolanieKIO"]["data"] is None:
        tags.append("no_header_date")
    if len(sp["pelnomocnicy"]) > 1:
        tags.append(f"{len(sp['pelnomocnicy'])} attorneys")
    return tags


def build_doc(client, C, doc, force, log):
    bdir = BUILD / C["id"]
    srcf = bdir / f"{doc}.txt"
    r = random.Random(f"{SEED}-{C['id']}-{doc}")
    instr = doc_instr(C, doc, r)
    facts = {"odwolanie": facts_odwolanie, "pelnomocnictwo": facts_pel, "przelew": facts_przelew}[doc](C, C["gt"][doc])
    req = required_strings(C, doc)
    ex = subprocess.run(["pdftotext", "-layout", str(TRAIN / C["source"] / DOCS[doc][0]), "-"], capture_output=True, text=True).stdout
    ex = ex[:3500 if doc == "odwolanie" else 1800]
    kind = {"odwolanie": "ODWOŁANIE do Krajowej Izby Odwoławczej", "pelnomocnictwo": "PEŁNOMOCNICTWO do reprezentowania wykonawcy w postępowaniu odwoławczym przed KIO",
            "przelew": "POTWIERDZENIE PRZELEWU (wydruk z bankowości internetowej)"}[doc]
    prompt = PROMPT.format(kind=kind, extra_rules="", facts=facts, required="\n".join(f"- {s}" for s in req),
                           instr="\n".join(f"- {s}" for s in instr), gt=json.dumps(C["gt"][doc], ensure_ascii=False, indent=2),
                           example=ex, markup=MARKUP)
    errs, notes, tries = [], [], 0
    if force or not srcf.exists():
        fb = ""
        for tries in range(1, 4):
            mt = 16000 if C["flags"].get("long") and doc == "odwolanie" else (9000 if doc == "odwolanie" else 4000)
            markup = generate(client, prompt + fb, mt)
            if C["flags"].get("long") and doc == "odwolanie" and len(markup.split()) < 4200:
                cont = generate(client, "Poniżej jest odwołanie. Napisz WYŁĄCZNIE dodatkowe sekcje uzasadnienia (ok. 2500 słów), które "
                                "zostaną wstawione przed sekcją wniosków/petitum: szersza analiza prawna zarzutów, orzecznictwo opisane "
                                "bez sygnatur i dat, wnioski dowodowe. Bez żadnych dat, numerów, kwot, nazw podmiotów innych niż "
                                "'Odwołujący', 'Zamawiający' i 'Izba'. Ten sam markup.\n\n" + MARKUP + "\n\nODWOŁANIE:\n" + markup, 8000)
                markup = insert_before_petitum(markup, cont)
            errs, notes = run_checks(C, doc, markup)
            srcf.parent.mkdir(parents=True, exist_ok=True)
            srcf.write_text(markup, encoding="utf-8")
            if not errs:
                break
            fb = ("\n\nUWAGA – poprzednia wersja dokumentu miała błędy, popraw je w nowej wersji:\n"
                  + "\n".join(f"- {e}" for e in errs[:15]))
            log(f"{C['id']}/{doc}: retry {tries}: {errs[:6]}")
    else:
        markup = srcf.read_text(encoding="utf-8")
        errs, notes = run_checks(C, doc, markup)
    out_pdf = OUT / C["id"] / DOCS[doc][0]
    render(markup, out_pdf, render_style(C, doc, r))
    pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(out_pdf)], capture_output=True, text=True).stdout).group(1))
    if C["flags"].get("long") and doc == "odwolanie" and pages < 8:
        notes.append(f"długie odwołanie ma tylko {pages} stron")
    # the rendered PDF text must still contain the GT digits (render sanity)
    pdf_txt = subprocess.run(["pdftotext", str(out_pdf), "-"], capture_output=True, text=True).stdout
    pdf_miss = [m for m in gt_check(C["gt"][doc], pdf_txt) if re.search(r"=\d{9,}$", m)]
    if pdf_miss:
        notes.append(f"render: cyfry nieodnalezione w PDF: {pdf_miss}")
    return {"doc": doc, "errors": errs, "notes": notes, "pages": pages, "tries": tries}


def insert_before_petitum(markup, extra):
    lines = markup.splitlines()
    for i, l in enumerate(lines):
        if re.search(r"(?i)^(##\s*)?([IVX]+\.|[A-Z]\.|\d+\.)?\s*(wnioski|wnoszę o|petitum|załączniki)", l.strip()) and i > len(lines) // 3:
            return "\n".join(lines[:i] + [""] + extra.splitlines() + [""] + lines[i:])
    return markup + "\n\n" + extra


NEG_DIR = OUT / "blind_negatywne"
NEGATIVES = {
    "postanowienie_KIO": "fragment (pierwsze 2 strony) ORZECZENIA Krajowej Izby Odwoławczej – wyrok z sygnaturą akt KIO, składem "
                         "orzekającym, rozstrzygnięciem (sentencja: uwzględnia/oddala odwołanie, koszty, wpis) i początkiem uzasadnienia. "
                         "Wymienia odwołującego, zamawiającego, przystępującego, tytuł i numer postępowania. To NIE jest odwołanie, tylko orzeczenie Izby.",
    "faktura_uslugi_prawne": "FAKTURA VAT wystawiona przez kancelarię dla wykonawcy za 'sporządzenie odwołania do KIO i reprezentację' – "
                             "sprzedawca, nabywca (NIP), pozycje, netto/VAT/brutto, termin płatności, numer rachunku do zapłaty. "
                             "To NIE jest potwierdzenie przelewu ani pełnomocnictwo.",
    "ogloszenie_o_zamowieniu": "OGŁOSZENIE O ZAMÓWIENIU w Biuletynie Zamówień Publicznych (układ sekcji: SEKCJA I – ZAMAWIAJĄCY, "
                               "SEKCJA II – INFORMACJE PODSTAWOWE z numerem ogłoszenia BZP i identyfikatorem postępowania, SEKCJA III – "
                               "UDOSTĘPNIANIE DOKUMENTÓW, SEKCJA IV – PRZEDMIOT ZAMÓWIENIA, terminy, wadium). To NIE jest odwołanie.",
}


def build_negatives(client, force):
    """Out-of-scope documents; expected output is {} (file named after the PDF stem)."""
    r = random.Random(f"{SEED}-neg")
    G = Gen(r)
    res = {}
    for stem, desc in NEGATIVES.items():
        a, b, z = G.company(), G.company(), G.public_entity()
        p1, p2 = G.person(), G.person()
        facts = (f"- wykonawca: {ent_line(a)}\n- inny wykonawca: {ent_line(b)}\n- zamawiający: {ent_line(z)}\n"
                 f"- osoby: {p1['name']}, {p2['name']}\n- tytuł zamówienia: {r.choice(TITLES).format(T=z['town'][0], T2=z['town'][0], Tloc=z['town'][1], Tgen=z['town'][0])}\n"
                 f"- numer postępowania: {nr_postepowania(r, 2026)}\n- numer BZP: {bzp_number(r, 2026).replace('BZP', 'BZP ')}\n"
                 f"- rachunek bankowy: {fmt_acc(iban(r), 'plspaced')}\n- daty: dowolne z 2026 r.")
        srcf = BUILD / "negatywne" / f"{stem}.txt"
        if force or not srcf.exists():
            prompt = (f"Jesteś generatorem realistycznych polskich dokumentów. Napisz dokument: {desc}\n"
                      f"Długość: 1–2 strony. Użyj danych:\n{facts}\nDane fikcyjne, numery tylko z listy. {MARKUP}")
            srcf.parent.mkdir(parents=True, exist_ok=True)
            srcf.write_text(generate(client, prompt, 5000), encoding="utf-8")
        render(srcf.read_text(encoding="utf-8"), NEG_DIR / f"{stem}.pdf", render_style({"przelew": None}, "odwolanie", r))
        (NEG_DIR / f"{stem}.json").write_text("{}\n", encoding="utf-8")
        res[stem] = {"expected": {}, "kind": desc.split(" – ")[0][:80]}
    return res


def credits():
    import urllib.request
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {os.environ['O2J_LLM_API_KEY']}"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]["total_usage"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--docs", nargs="*", default=list(DOCS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--plan", action="store_true", help="only print the plan and GT, no LLM calls")
    ap.add_argument("--negatives", action="store_true", help="(re)build only the out-of-scope documents")
    a = ap.parse_args(argv)
    plans = plan_cases()
    cases = []
    for i, src, diffs in plans:
        C = build_case(i, src, diffs)
        C["gt"] = build_gt(C)
        cases.append(C)
    sel = [C for C in cases if not a.only or C["id"] in a.only]
    for C in sel:
        d = OUT / C["id"]
        d.mkdir(parents=True, exist_ok=True)
        for doc in DOCS:
            (d / DOCS[doc][1]).write_text(json.dumps(C["gt"][doc], ensure_ascii=False, indent=2), encoding="utf-8")
    if a.plan:
        for C in sel:
            print(C["id"], C["source"], C["diffs"], C["flags"])
        return
    client = llm_client()
    u0 = credits()
    if a.negatives:
        neg = build_negatives(client, a.force)
        man = OUT / "_manifest.json"
        m = json.loads(man.read_text()) if man.exists() else {}
        m["negatives"] = neg
        man.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"negatives built, cost ${COST['usd']:.3f}")
        return
    rep_path = BUILD / "_check.json"
    rep = json.loads(rep_path.read_text()) if rep_path.exists() else {}
    lock = threading.Lock()

    def log(s):
        with lock:
            print(s, flush=True)
    jobs = [(C, doc) for C in sel for doc in a.docs]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(build_doc, client, C, doc, a.force, log): (C, doc) for C, doc in jobs}
        for f in as_completed(futs):
            C, doc = futs[f]
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = {"doc": doc, "errors": [f"EXC {e!r}"], "notes": []}
            rep.setdefault(C["id"], {})[doc] = res
            log(f"{C['id']}/{doc}: " + ("OK" if not res["errors"] else f"ERR {res['errors'][:5]}")
                + (f"  notes={res['notes'][:3]}" if res["notes"] else "") + f"  cost=${COST['usd']:.3f}")
    BUILD.mkdir(parents=True, exist_ok=True)
    rep_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"seed": SEED, "generator": "eval/make_blind.py", "model": MODEL, "cases": {}}
    for C in cases:
        manifest["cases"][C["id"]] = {
            "source_case": C["source"], "difficulties": C["diffs"], "inherited_structure": inherited(C, C["source"]),
            "params": {k: v for k, v in C["flags"].items()}, "czynnosc_powod_id": C["powod"],
            "header": C["header"] | {"line": C["header_line"]}, "bank": C["przelew"]["bank"]["name"],
            "amount_notation": fmt_money(C["przelew"]["kwota"], C["przelew"]["amount_style"]),
            "checks": rep.get(C["id"], {})}
    old = OUT / "_manifest.json"
    if old.exists():
        prev = json.loads(old.read_text())
        if "negatives" in prev:
            manifest["negatives"] = prev["negatives"]
        for cid, v in prev.get("cases", {}).items():  # keep checks of cases not rebuilt in this run
            if a.only and cid not in a.only and cid in manifest["cases"]:
                manifest["cases"][cid]["checks"] = v.get("checks", {})
    old.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    u1 = credits()
    print(f"\nrun cost (tracked) ${COST['usd']:.3f}; OpenRouter usage delta ${u1 - u0:.3f}")


if __name__ == "__main__":
    sys.exit(main())
