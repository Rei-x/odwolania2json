"""Hard synthetic test set: LLM-rewritten variants of training cases with edited ground truth.

For each VARIANT below:
  1. target GT = deep copy of data/train/<case>/*.json, patched by the variant's `patch`
  2. a strong LLM rewrites each original document (pdftotext) following the variant's
     instructions so that it implies exactly the target GT
  3. the rewrite (light markup) is rendered to PDF with reportlab
  4. a consistency check looks for every non-null GT value in the generated text

Output: data/variants/<case>_<tag>/{odwolanie,pelnomocnictwo,potwierdzenie_przelewu}.pdf
        + odwolanie.json / pelnomocnictwo.json / przelew.json (+ _src/*.txt markup, _check.json)

Usage: python -m eval.make_variants [--only TAG ...] [--force] [--model M] [--workers 6]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "data" / "train"
OUT = ROOT / "data" / "variants"
DOCS = {  # doctype -> (pdf name, gt json name)
    "odwolanie": ("odwolanie.pdf", "odwolanie.json"),
    "pelnomocnictwo": ("pelnomocnictwo.pdf", "pelnomocnictwo.json"),
    "przelew": ("potwierdzenie_przelewu.pdf", "przelew.json"),
}

# ----------------------------------------------------------------------------- variants
# Each doc instruction is free text for the LLM; `patch(o, p, t)` mutates the GT copies
# (o = odwolanie, p = pelnomocnictwo, t = przelew).


def _noop(o, p, t):
    pass


def p_02(o, p, t):
    pass


def p_03(o, p, t):
    p["pelnomocnicy"][0]["pesel"] = "88031512347"


def p_05(o, p, t):
    p["mocodawca"].insert(0, {"data": {"imie_nazwisko": None, "krs": "9998123401", "nazwa": "Tarvona Instal sp. z o.o.",
                                       "nip": "9991234567", "typ": "osoba_prawna"},
                              "podpisujacy": [{"imie_nazwisko": "Wiesław Grabowski"}]})


def p_07(o, p, t):
    o["Zamawiajacy"][0]["prowadzacy_postepowanie"] = 1
    o["Zamawiajacy"].insert(0, {"krs": None, "nazwa": "Gmina Wiśniowa Góra", "nip": "9995551112", "regon": "999888777",
                                "prowadzacy_postepowanie": 0})
    o["ZamowieniePubliczne"]["numer_bzp"] = "2026/BZP00999042/01"


def p_10(o, p, t):
    od = o["Odwolujacy"][0]
    od["nazwa"], od["krs"] = "MERIDIAN KONSULTING Patryk Mazur", None
    od["pelnomocnik"]["mail"] = None
    m = p["mocodawca"][0]
    m["data"].update(imie_nazwisko="Patryk Mazur", krs=None, nazwa="MERIDIAN KONSULTING Patryk Mazur",
                     typ="osoba_fizyczna")
    m["podpisujacy"] = [{"imie_nazwisko": "Patryk Mazur"}]


def p_12(o, p, t):
    o["Odwolujacy"][0]["pelnomocnik"]["mail"] = None
    p["pelnomocnicy"] = [{"imie_nazwisko": "Klaudia Dobrowolski", "pesel": "85050512346"},
                         {"imie_nazwisko": "Tomasz Grabarczyk", "pesel": "79110304512"},
                         {"imie_nazwisko": "Ewa Lis", "pesel": "90020211223"}]


def p_21(o, p, t):
    o["OdwolanieKIO"]["czynnosc_dzien"] = None
    o["ZamowieniePubliczne"]["numer_bzp"] = None
    o["ZamowieniePubliczne"]["numer_ted"] = None


def p_30(o, p, t):
    p["pelnomocnicy"][0]["pesel"] = "82071712345"
    t["przelew_bankowy"].update(kwota=15000.0, na_rachunek="39101010100036862231000000",
                                tytul="Wpis od odwołania - postępowanie DI.123.2026 - Kadmos Rozwiązania sp. k.")


def p_35(o, p, t):
    o["Odwolujacy"][0]["pelnomocnik"]["mail"] = None
    o["ZamowieniePubliczne"]["numer_ted"] = "999000-2026"


def p_53(o, p, t):
    o["Zamawiajacy"][0]["prowadzacy_postepowanie"] = 1
    o["Zamawiajacy"].insert(0, {"krs": None, "nazwa": "Gmina Zalesie Królewskie", "nip": "9996661234",
                                "regon": "999777555", "prowadzacy_postepowanie": 0})


def p_57(o, p, t):
    o["ZamowieniePubliczne"]["numer_bzp"] = None
    o["ZamowieniePubliczne"]["numer_ted"] = None
    p["pelnomocnicy"][0]["pesel"] = "76120807654"


VARIANTS = [
    dict(case="przyklad_02", tag="layout", patch=p_02, docs={
        "odwolanie": "Zamień kolejność bloków: najpierw blok 'Zamawiający', potem 'Odwołujący'. Linię miejscowości i daty "
                     "zapisz w prawym górnym rogu w formacie 'Gdańsk, 03.09.2026 r.'. Sekcję 'dotyczy' przepisz jako listę etykiet: "
                     "'Nazwa zamówienia:', 'Znak sprawy:', 'Ogłoszenie w Dz. Urz. UE:' z numerem TED zapisanym jako '2026/S 170-999073'.",
        "pelnomocnictwo": "Struktura paragrafowa (§ 1, § 2...). Data w formacie '3 IX 2026 r.'. Pełnomocników podaj w celowniku: "
                          "'udziela pełnomocnictwa Bartoszowi Szymanskiemu oraz Cezaremu Wierzbickiemu'.",
        "przelew": "Układ dwukolumnowy: wiersz nagłówkowy tabeli 'Nadawca || Odbiorca', pod nim nazwy, adresy i numery rachunków "
                   "w obu kolumnach. Zamiast etykiety 'Rachunek zleceniodawcy' użyj 'Rachunek obciążany'. Kwotę zapisz jako 'PLN 50,00'.",
    }),
    dict(case="przyklad_03", tag="relative_date_list", patch=p_03, docs={
        "odwolanie": "Usuń zdanie 'Zamawiający w dniu ... nie wykluczył...'. Zamiast niego po 'wnoszę odwołanie wobec czynności i zaniechań "
                     "Zamawiającego, polegających na:' daj listę: '1) zaniechaniu wykluczenia z postępowania wykonawcy Bravento Systemy "
                     "sp. z o.o. (KRS 0000456123), o którego wyborze Zamawiający poinformował w dniu 16 lutego br.; 2) wyborze oferty "
                     "Bravento Systemy sp. z o.o. jako najkorzystniejszej'. Nagłówek 'Bydgoszcz, dnia 2 marca 2026 roku' zostaw. "
                     "KRS Bravento podaj TYLKO w liście czynności, nie w blokach stron.",
        "pelnomocnictwo": "Pełnomocnika podaj w celowniku ('udziela pełnomocnictwa adwokatowi Norbertowi Szulcowi') i dodaj jego "
                          "PESEL 88031512347.",
        "przelew": "Kwotę podaj jako '50,00 zł (słownie: pięćdziesiąt złotych 00/100)'. Numery rachunków z prefiksem PL i spacjami "
                   "co 4 cyfry.",
    }),
    dict(case="przyklad_05", tag="consortium", patch=p_05, docs={
        "odwolanie": "Odwołujący to konsorcjum. W bloku 'Odwołujący' NAJPIERW podaj partnera: 'Partner Konsorcjum: Tarvona Instal sp. z o.o., "
                     "ul. Fabryczna 12, 20-301 Lublin, KRS: 9998123401, NIP: 9991234567, REGON: 999345671', a DOPIERO POTEM "
                     "'Lider Konsorcjum (pełnomocnik Konsorcjum):' Corvantis Wyposażenie sp. z o.o. z jego danymi. "
                     "Pełnomocnik konsorcjum (osoba) i kancelaria bez zmian.",
        "pelnomocnictwo": "Pełnomocnictwa udzielają wspólnie dwaj konsorcjanci: 1) Tarvona Instal sp. z o.o., ul. Fabryczna 12, 20-301 Lublin, "
                          "KRS 9998123401, NIP 9991234567 (w imieniu której podpisuje Wiesław Grabowski – Prezes Zarządu) oraz "
                          "2) Corvantis Wyposażenie sp. z o.o. (dane i podpisujący jak w oryginale). Osobne bloki podpisów dla każdego.",
        "przelew": "Datę operacji zapisz jako '26.10.2026 r.'. Etykietę numeru transakcji zmień na 'Identyfikator operacji'.",
    }),
    dict(case="przyklad_07", tag="multi_zamawiajacy", patch=p_07, docs={
        "odwolanie": "Zamawiający wspólni (art. 38 Pzp). W bloku Zamawiających NAJPIERW: 'Zamawiający 1: Gmina Wiśniowa Góra, ul. Rynek 1, "
                     "32-400 Wiśniowa Góra, NIP: 9995551112, REGON: 999888777' (bez KRS), POTEM 'Zamawiający 2 – pełnomocnik "
                     "Zamawiających, prowadzący postępowanie: Ilystera Automatyka sp. k.' z jej danymi. Data nagłówka '15 VII 2026 r.' "
                     "(miejscowość Warszawa). Numer BZP zapisz jako 'nr ogłoszenia: 2026/BZP 00999042/01' (korekta ogłoszenia).",
        "pelnomocnictwo": "Postępowanie 'prowadzone przez Ilystera Automatyka sp. k. działającą także w imieniu Gminy Wiśniowa Góra'. "
                          "Reszta jak w oryginale, inne sformułowania.",
        "przelew": "Numery rachunków z prefiksem 'PL' i spacjami co 4 cyfry. Data w formacie ISO.",
    }),
    dict(case="przyklad_10", tag="sole_trader", patch=p_10, docs={
        "odwolanie": "Odwołujący jest przedsiębiorcą – osobą fizyczną: 'Patryk Mazur prowadzący działalność gospodarczą pod firmą "
                     "MERIDIAN KONSULTING Patryk Mazur', wpisany do CEIDG (BEZ KRS), NIP i REGON jak w oryginale. Pełnomocnik "
                     "'r.pr. Patrycja Rutkiewicz', kancelaria jak w oryginale, ale BEZ adresu e-mail (podaj tylko telefon).",
        "pelnomocnictwo": "'Ja, niżej podpisany Patryk Mazur, prowadzący działalność gospodarczą pod firmą MERIDIAN KONSULTING Patryk Mazur, "
                          "NIP ..., REGON ... (CEIDG), udzielam pełnomocnictwa Patrycji Rutkiewicz oraz Markowi Łukaszewskiemu' "
                          "(celownik). Podpisuje tylko Patryk Mazur.",
        "przelew": "Zleceniodawca: 'MERIDIAN KONSULTING Patryk Mazur'. Kwota '200,00 PLN'. Zachowaj tytuł przelewu dokładnie.",
    }),
    dict(case="przyklad_12", tag="pesel_multi_pel", patch=p_12, docs={
        "odwolanie": "Odwołujący reprezentowany przez: 'radca prawny Klaudia Dobrowolski, adw. Tomasz Grabarczyk'. Adres do korespondencji "
                     "kancelarii bez e-maila. W sekcji 'dotyczy' dodaj zdanie 'W sprawie tego postępowania toczyło się już postępowanie "
                     "odwoławcze o sygn. akt KIO 1234/26.'",
        "pelnomocnictwo": "Ustanawia się pełnomocnikami: '1) radcę prawnego Klaudię Dobrowolski, PESEL 85050512346, 2) adwokata Tomasza "
                          "Grabarczyka, PESEL 79110304512, 3) aplikantkę adwokacką Ewę Lis, PESEL 90020211223' (biernik).",
        "przelew": "Etykieta 'Rachunek obciążany' dla rachunku zleceniodawcy, data ISO, kwota '200.00 zł'.",
    }),
    dict(case="przyklad_15", tag="act_in_zarzuty", patch=_noop, docs={
        "odwolanie": "Usuń zdanie 'Zamawiający w dniu ... ogłosił wybór oferty'. Pierwsza zaskarżona czynność ma się pojawić TYLKO w zarzutach: "
                     "'Zarzut nr 1 – naruszenie art. 239 ust. 1 Pzp poprzez dokonanie w dniu 27 grudnia 2025 r. wyboru jako "
                     "najkorzystniejszej oferty wykonawcy Lumenix Polska S.A.'. Nagłówek z datą słownie: 'Poznań, dnia dwunastego "
                     "stycznia 2026 r.'.",
        "pelnomocnictwo": "Lekka parafraza, data dokumentu zapisana słownie.",
        "przelew": "Wydruk 'Szczegóły operacji' w formie listy 'etykieta: wartość' z etykietami 'Z rachunku', 'Na rachunek', "
                   "'Kwota', 'Data waluty', 'Tytułem', 'Nr ref.'.",
    }),
    dict(case="przyklad_18", tag="ted_bzp_formats", patch=_noop, docs={
        "odwolanie": "Numer BZP zapisz jako 'ogłoszenie nr 2026/BZP 00999497/03 z dnia 5 sierpnia 2026 r.' a numer TED jako "
                     "'Dz.Urz.UE 2026/S 158-999124'. Data nagłówka w formacie ISO: 'Katowice, 2026-08-28'. Pełnomocnik zapisany "
                     "jako 'radca prawny Dorota Zawadzki'.",
        "pelnomocnictwo": "Lekka parafraza; pełnomocnik z tytułem 'radca prawny' po nazwisku: 'Dorota Zawadzki, radca prawny'.",
        "przelew": "Kwotę podaj liczbowo i słownie: '17,00 PLN (siedemnaście złotych 00/100)'.",
    }),
    dict(case="przyklad_21", tag="no_act_date_no_numbers", patch=p_21, docs={
        "odwolanie": "Usuń zdanie z datą czynności. Pierwsza czynność: 'zaniechanie odrzucenia oferty wykonawcy Cerbex Instal sp. z o.o.' "
                     "— BEZ podania jakiejkolwiek daty tej czynności ani daty zawiadomienia. Dodaj zdanie 'Otwarcie ofert nastąpiło "
                     "w dniu 10 marca 2026 r.'. Usuń całkowicie numery BZP i TED (zostaw tylko nr referencyjny SWZ.429.2026). "
                     "Nagłówek: 'Kraków, 04.04.2026 r.'.",
        "pelnomocnictwo": "Lekka parafraza.",
        "przelew": "Układ dwukolumnowy tabeli: 'Zleceniodawca || Beneficjent' z rachunkami pod nazwami.",
    }),
    dict(case="przyklad_26", tag="misleading_header", patch=_noop, docs={
        "odwolanie": "W nagłówku pod linią 'Wrocław, 18 czerwca 2026 r.' dodaj linię 'dot. wyroku KIO z dnia 2 czerwca 2026 r., sygn. akt "
                     "KIO 1500/26'. W bloku pełnomocnika podaj kancelarię jako 'Kancelaria Prawna i Partnerzy sp.p., KRS 0000765432' "
                     "(ten KRS NIE jest KRS-em Odwołującego). Pełnomocnik zapisany jako 'mec. Ryszard Mazurkiewicz'.",
        "pelnomocnictwo": "Pełnomocników w celowniku: 'udziela pełnomocnictwa Ryszardowi Mazurkiewiczowi i Patrycji Głowacz'.",
        "przelew": "Kwota '34.00 PLN', rachunki z prefiksem PL bez spacji.",
    }),
    dict(case="przyklad_30", tag="wpis_amount_bottom_date", patch=p_30, docs={
        "odwolanie": "Usuń linię miejscowości i daty z góry strony; umieść ją NA KOŃCU dokumentu nad podpisem: 'Łódź, dnia 27 czerwca 2026 r.'.",
        "pelnomocnictwo": "Dodaj PESEL pełnomocnika: 82071712345. Pełnomocnik w celowniku ('Grzegorzowi Rutkiewiczowi').",
        "przelew": "To przelew WPISU od odwołania (nie opłata skarbowa): odbiorca 'Urząd Zamówień Publicznych, ul. Postępu 17A, 02-676 Warszawa', "
                   "rachunek odbiorcy 'PL39 1010 1010 0036 8622 3100 0000', kwota '15.000,00 zł', tytuł dokładnie: 'Wpis od odwołania - "
                   "postępowanie DI.123.2026 - Kadmos Rozwiązania sp. k.'. Rachunek nadawcy, data i numer transakcji jak w oryginale.",
    }),
    dict(case="przyklad_35", tag="pel_accusative_nomail", patch=p_35, docs={
        "odwolanie": "Blok odwołującego: 'reprezentowany przez r.pr. Klaudię Szymanski oraz r.pr. Norberta Sadowskiego' (biernik), "
                     "adres kancelarii bez e-maila. Numer TED zapisz jako '2026/S 040-999000'.",
        "pelnomocnictwo": "Pełnomocnicy z tytułami: 'radca prawny Klaudia Szymanski' i 'radca prawny Norbert Sadowski'.",
        "przelew": "Rachunki ze spacjami (bez PL). Etykieta daty: 'Data księgowania'.",
    }),
    dict(case="przyklad_47", tag="sole_trader_dative", patch=_noop, docs={
        "odwolanie": "Data nagłówka '28 VIII 2026 r.' (miejscowość Poznań). Lekka parafraza bloków stron.",
        "pelnomocnictwo": "'Ja, Sebastian Tomaszewski, prowadzący działalność gospodarczą pod firmą RAVELO-BUD Sebastian Tomaszewski ... "
                          "udzielam pełnomocnictwa Elżbiecie Woźniak oraz Iwonie Kucharskiej' (celownik).",
        "przelew": "Kwota 'PLN 100', etykieta 'Rachunek obciążany'.",
    }),
    dict(case="przyklad_53", tag="multi_zam_implicit", patch=p_53, docs={
        "odwolanie": "Zamawiający wspólni. Blok 'Zamawiający:' wymienia NAJPIERW 'Gmina Zalesie Królewskie, ul. Kościelna 2, NIP: 9996661234, "
                     "REGON: 999777555' (bez KRS), potem oryginalnego zamawiającego (Zakład Usług Komunalnych...). Prowadzącego NIE oznaczaj "
                     "etykietą w bloku — zamiast tego w treści dodaj zdanie: 'Postępowanie w imieniu obu Zamawiających prowadzi Zakład "
                     "Usług Komunalnych w Zalesiu Królewskim sp. z o.o.'.",
        "pelnomocnictwo": "Pełnomocników w celowniku: 'udziela pełnomocnictwa Celinie Ostrowskiej i Barbarze Piotrowskiej'.",
        "przelew": "Kwota liczbowo i słownie.",
    }),
    dict(case="przyklad_57", tag="no_numbers_iso", patch=p_57, docs={
        "odwolanie": "Usuń numer ogłoszenia BZP (żadnych numerów BZP/TED). Numer postępowania pod etykietą 'Znak sprawy: ZP.50.2026'. "
                     "Data nagłówka ISO: 'Koszalin, 2026-06-16'. Pierwsza czynność w liście: '1) unieważnieniu postępowania "
                     "(zawiadomienie z dnia 9.06.2026 r.)'.",
        "pelnomocnictwo": "Dodaj PESEL pełnomocnika 76120807654.",
        "przelew": "Układ dwukolumnowy (etykieta || wartość), data '9 czerwca 2026' -> zachowaj datę z oryginału, ale zapisz ją w formacie DD.MM.RRRR.",
    }),
]

# ----------------------------------------------------------------------------- LLM
MARKUP = """Format wyjścia (prosty markup, jedna linia = jeden akapit/wiersz):
- '# TEKST'  -> wyśrodkowany pogrubiony tytuł (np. ODWOŁANIE)
- '>> TEKST' -> linia wyrównana do prawej (np. miejscowość i data, adresat)
- 'A || B'   -> wiersz tabeli dwukolumnowej (kolejne takie linie tworzą jedną tabelę; dla 3 kolumn 'A || B || C')
- '---'      -> podział strony
- pusta linia -> odstęp
- inne linie -> zwykły akapit (tekst zawijany automatycznie; NIE łam zdań ręcznie)
Zwróć WYŁĄCZNIE treść dokumentu w tym formacie, bez komentarzy, bez bloków kodu."""

PROMPT = """Jesteś generatorem realistycznych polskich dokumentów prawnych/bankowych do testowania systemu ekstrakcji danych.
Przepisz poniższy ORYGINALNY dokument ({doctype}) tak, aby wyglądał jak inny, realistyczny dokument tej samej sprawy,
z innym układem i sformułowaniami, stosując WYMAGANE ZMIANY.

ŻELAZNE ZASADY:
1. Dokument musi jednoznacznie wynikać z DOCELOWEGO JSON-a (ground truth): każda niepusta wartość musi dać się z niego
   odczytać (nazwy podmiotów, numery KRS/NIP/REGON/rachunków, kwoty, daty, numery postępowań — dokładnie te wartości,
   choć format zapisu dat/kwot/numerów może być inny, jeśli tak każą WYMAGANE ZMIANY).
2. Wartości null w docelowym JSON-ie NIE mogą występować w dokumencie (np. null e-mail = brak e-maila pełnomocnika).
3. Nie dodawaj nowych identyfikatorów, dat, osób ani podmiotów poza oryginałem i WYMAGANYMI ZMIANAMI.
4. Nie zmieniaj liter w nazwach własnych (poza odmianą przez przypadki, jeśli tak każą WYMAGANE ZMIANY).
5. Treść merytoryczną (zarzuty, uzasadnienie, pouczenia) możesz skrócić i sparafrazować; odwołanie ma mieć 2–3 strony,
   pozostałe dokumenty 1 stronę. W odwołaniu zachowaj pierwszą zaskarżoną czynność zgodną z czynnosc_powod_id
   ({powod}) i datą czynnosc_dzien, chyba że WYMAGANE ZMIANY mówią inaczej.
6. Tytuł przelewu (pole tytul) przepisz znak w znak.
7. NIE cytuj w dokumencie kanonicznych etykiet z JSON-a (np. 'Decyzja o odrzuceniu oferty') ani nazw pól — opisz czynność
   naturalnym językiem pisma procesowego, tak jak w oryginale.

WYMAGANE ZMIANY:
{instr}

DOCELOWY JSON (ground truth):
{gt}

ORYGINALNY DOKUMENT (tekst z PDF, układ może być zniekształcony):
{text}

{markup}"""


def llm_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(ROOT / ".env")
    return OpenAI(base_url=os.environ.get("O2J_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
                  api_key=os.environ["O2J_LLM_API_KEY"], timeout=600)


def generate(client, model: str, prompt: str) -> str:
    last = None
    for _ in range(3):
        try:
            r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                               temperature=0.4, max_tokens=12000)
            s = (r.choices[0].message.content or "").strip()
            s = re.sub(r"^<think>.*?</think>", "", s, flags=re.S).strip()
            s = re.sub(r"^```\w*\n|\n```$", "", s).strip()
            if len(s) > 200:
                return s
            last = RuntimeError(f"short output: {s[:200]!r}")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


# ----------------------------------------------------------------------------- render
def render(markup: str, out: Path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if "Arial" not in pdfmetrics.getRegisteredFontNames():
        sup = "/System/Library/Fonts/Supplemental/"
        pdfmetrics.registerFont(TTFont("Arial", sup + "Arial.ttf"))
        pdfmetrics.registerFont(TTFont("Arial-Bold", sup + "Arial Bold.ttf"))
    body = ParagraphStyle("b", fontName="Arial", fontSize=10, leading=13, alignment=TA_LEFT)
    right = ParagraphStyle("r", parent=body, alignment=TA_RIGHT)
    title = ParagraphStyle("t", parent=body, fontName="Arial-Bold", fontSize=14, leading=18, alignment=TA_CENTER,
                           spaceBefore=6, spaceAfter=6)
    cell = ParagraphStyle("c", parent=body, fontSize=9.5, leading=12)
    story, table = [], []

    def flush():
        if table:
            ncol = max(len(r) for r in table)
            rows = [[Paragraph(escape(c.strip()), cell) for c in r] + [""] * (ncol - len(r)) for r in table]
            t = Table(rows, colWidths=[(A4[0] - 4 * cm) / ncol] * ncol)
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
            story.append(t)
            story.append(Spacer(1, 6))
            table.clear()

    for line in markup.splitlines():
        s = line.rstrip()
        if "||" in s:
            table.append(s.split("||"))
            continue
        flush()
        if not s.strip():
            story.append(Spacer(1, 6))
        elif s.strip() == "---":
            story.append(PageBreak())
        elif s.startswith("# "):
            story.append(Paragraph(escape(s[2:].strip()), title))
        elif s.startswith(">>"):
            story.append(Paragraph(escape(s[2:].strip()), right))
        else:
            story.append(Paragraph(escape(s.strip()), body))
    flush()
    out.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm,
                      bottomMargin=2 * cm).build(story)


# ----------------------------------------------------------------------------- consistency check
MONTHS_GEN = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
              "października", "listopada", "grudnia"]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, x


def check(gt: dict, text: str) -> list[str]:
    """Return GT leaves whose value cannot be found in the generated text (needs manual review)."""
    flat = " ".join(text.split()).lower()
    dig = re.sub(r"\D", "", text)
    miss = []
    for path, v in _leaves(gt):
        leaf = path.split(".")[-1]
        if v is None or leaf in ("czynnosc_powod_id", "czynnosc_opis", "przez-pelnomocnika", "prowadzacy_postepowanie", "typ"):
            continue
        s = str(v)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            y, m, d = map(int, s.split("-"))
            forms = [s, f"{d:02d}.{m:02d}.{y}", f"{d}.{m:02d}.{y}", f"{d} {MONTHS_GEN[m-1]} {y}",
                     f"{d} {ROMAN[m-1].lower()} {y}", f"{d:02d} {MONTHS_GEN[m-1]} {y}"]
            if not any(f.lower() in flat for f in forms):
                miss.append(f"{path}={s}")
        elif re.fullmatch(r"\d{6,}", s):
            if s not in dig:
                miss.append(f"{path}={s}")
        elif isinstance(v, (int, float)):
            continue
        elif " ".join(s.split()).lower() not in flat:
            miss.append(f"{path}={s}")
    return miss


# ----------------------------------------------------------------------------- main
def pdftext(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


def build_one(client, model, v, doctype, force) -> dict:
    case, tag = v["case"], v["tag"]
    vdir = OUT / f"{case}_{tag}"
    pdf_name, js_name = DOCS[doctype]
    gts = {d: json.loads((TRAIN / case / DOCS[d][1]).read_text()) for d in DOCS}
    gts = copy.deepcopy(gts)
    v["patch"](gts["odwolanie"], gts["pelnomocnictwo"], gts["przelew"])
    gt = gts[doctype]
    (vdir / js_name).parent.mkdir(parents=True, exist_ok=True)
    (vdir / js_name).write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    src = vdir / "_src" / f"{doctype}.txt"
    if force or not src.exists():
        orig = pdftext(TRAIN / case / pdf_name)
        if doctype == "odwolanie":
            orig = orig[:7000]
        powod = f"{gts['odwolanie']['OdwolanieKIO']['czynnosc_powod_id']} = {gts['odwolanie']['OdwolanieKIO']['czynnosc_opis']}"
        prompt = PROMPT.format(doctype=doctype, instr=v["docs"].get(doctype, "Lekka parafraza i zmiana układu."),
                               gt=json.dumps(gt, ensure_ascii=False, indent=2), text=orig, powod=powod, markup=MARKUP)
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(generate(client, model, prompt), encoding="utf-8")
    markup = src.read_text(encoding="utf-8")
    render(markup, vdir / pdf_name)
    miss = check(gt, pdftext(vdir / pdf_name))
    return {"variant": vdir.name, "doctype": doctype, "missing_in_text": miss}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="variant tags or case names")
    ap.add_argument("--force", action="store_true", help="regenerate LLM text even if cached")
    ap.add_argument("--model", default="moonshotai/kimi-k3.1-pro")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    vs = [v for v in VARIANTS if not a.only or v["tag"] in a.only or v["case"] in a.only]
    client = llm_client()
    jobs = [(v, d) for v in vs for d in DOCS]
    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(build_one, client, a.model, v, d, a.force): (v, d) for v, d in jobs}
        for f in as_completed(futs):
            v, d = futs[f]
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                r = {"variant": f"{v['case']}_{v['tag']}", "doctype": d, "error": repr(e)}
            results.append(r)
            print(f"[{len(results)}/{len(jobs)}] {r['variant']}/{d}: "
                  + (r.get("error") or ("OK" if not r["missing_in_text"] else f"CHECK {r['missing_in_text']}")), flush=True)
    rep = OUT / "_check.json"
    old = json.loads(rep.read_text()) if rep.exists() else []
    keep = {(r["variant"], r["doctype"]) for r in results}
    rep.write_text(json.dumps([r for r in old if (r["variant"], r["doctype"]) not in keep] + results,
                              ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
