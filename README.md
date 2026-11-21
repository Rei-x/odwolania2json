# Odwołania2JSON

PDF-y sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) zamieniane na JSON zgodny ze schematami UZP. Każde pole ma dowód: stronę i cytat z dokumentu.

## Szybki start

```bash
cp .env.example .env            # uzupełnij klucz API
./start.sh                      # Windows: start.bat
```

Pliki z `./input/<sprawa>/*.pdf` trafiają do `./output/<sprawa>/*.json`. Wynikowy JSON ma taką samą nazwę jak plik wejściowy. Ślady ekstrakcji (klasyfikacja, model, dowody dla pól) zapisują się w `./trace/`.

GUI: `python gui.py` (Windows: `gui.bat`), adres http://127.0.0.1:8000. Wgrywasz PDF i widzisz podgląd dokumentu obok JSON. Kliknięcie pola pokazuje cytat i przewija PDF do właściwej strony.

Ewaluacja F1 na danych treningowych liczona według reguł organizatora: `python run.py eval [--cases N] [--model M] [--src data/scans]`.

## Jak to działa

```
PDF ─► warstwa tekstowa (pypdfium2) ──┐
   └─► skan? → OCR modelem wizyjnym ──┴─► klasyfikacja (reguły z YAML, LLM gdy niepewne)
        ─► ekstrakcja LLM (JSON Schema ze specyfikacji, few-shot z data/train)
        ─► normalizacja deterministyczna (daty, NIP/KRS/REGON, IBAN, BZP, TED, kwoty, tytuły osób)
        ─► pola pochodne (np. czynnosc_opis z czynnosc_powod_id)
        ─► grounding: każda wartość lokalizowana w tekście (strona + cytat)
```

Szybkość w profilu `auto` (domyślnym):
- Klasyfikacja bez LLM, gdy reguły wygrywają z przewagą >= 7 (`classification.skip_llm_margin`); dokumenty niejednoznaczne i możliwe spoza puli nadal potwierdza głosowanie 8B + 3B (równolegle). Próg dobrany w `eval/cls_margin.py`.
- Dokumenty digitalne: Ministral 3B, trudne eskalują do 8B. Skany (OCR): od razu Ministral 8B (`router.scan_model`), bez przebiegu 3B.
- OCR stron równolegle (maks. 3 strony, 12 zapytań naraz), krótkie limity czasu, a zapytanie bez odpowiedzi po 30-40 s dostaje duplikat i wygrywa szybsza odpowiedź.
- Pomiar: `python -m eval.speed_bench` (dokumenty po kolei, czas kroków, koszt, F1).

Decyzje projektowe oparte na literaturze:
- Na dokumentach szablonowych tekst i obraz dają podobną jakość, więc idziemy warstwą tekstową, a obraz służy tylko do OCR skanów.
- Constrained decoding z ograniczeniami domenowymi w schemacie (enum, typy) pomaga, o ile prompt jest zgodny ze schematem.
- Listy nie mają `minItems`, bo modele dopychają wtedy nieistotne pozycje.
- Własny grounding, bo VLM-y domyślnie nie podają źródła wartości.

## Nowy typ dokumentu bez zmian w kodzie

Wystarczy dodać plik `config/doctypes/<nazwa>.yaml`:

```yaml
name: faktura
description: Faktura VAT
classify:
  keywords: {'FAKTURA( VAT)?': 5, 'Sprzedawca': 2, 'Nabywca': 2}
  filename: [faktura]
pages: 2
few_shot: 2
examples: {pdf: faktura.pdf, json: faktura.json}   # opcjonalne przykłady w data/train/<sprawa>/
instructions: |
  - Kwoty jako liczby.
fields:
  faktura:
    type: object
    properties:
      numer: {type: string, description: Numer faktury}
      data_wystawienia: {type: date}
      nip_sprzedawcy: {type: string, normalize: [nip]}
      kwota_brutto: {type: number}
      pozycje:
        type: array
        items:
          type: object
          properties:
            nazwa: {type: string}
            wartosc: {type: number}
```

Dostępne typy pól: `string`, `date`, `integer`, `number`, `enum` (wartości z etykietami), `object`, `array`. Normalizatory: `date`, `nip`, `krs`, `regon`, `pesel`, `iban`, `bzp`, `ted`, `amount`, `person`, `city`, `digits`, `strip`. Pole pochodne: `derive: {label_of: <pole enum>}`.

## Model

Działa z każdym API zgodnym z OpenAI, które serwuje model o otwartych wagach. Konfiguracja jest w `.env` / `config/settings.yaml`. Domyślny model to `moonshotai/kimi-k3.1-pro` (open-weight, obsługuje tekst i obraz).

## Wyniki (data/train, 60 spraw, 180 dokumentów)

| Model | F1 |
|---|---|
| Kimi K3.1 Pro + weryfikacja/naprawa | 1.0000 |

## Pętla agentowa: weryfikacja → naprawa

Po ekstrakcji walidatory z YAML sprawdzają każde pole:
- `pattern`: zgodność formatu,
- `single_person`: w polu jest jedna osoba,
- grounding: wartość występuje w tekście dokumentu.

Pola, które nie przeszły, wracają do LLM razem z opisem problemu i dokumentem. Model poprawia tylko te pola i uzasadnia każdą zmianę cytatem. Potem następuje ponowna weryfikacja, maksymalnie `verify.max_rounds` rund. Wszystkie poprawki są zapisane w `trace/` i widoczne w GUI.
