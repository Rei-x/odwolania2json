# Odwołania2JSON

PDF-y sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) zamieniane na JSON zgodny ze schematami UZP. Każde pole ma dowód: stronę i cytat z dokumentu.

## Szybki start

```bash
cp .env.example .env            # uzupełnij klucz API
./start.sh                      # Windows: start.bat
```

Pliki z `./input/<sprawa>/*.pdf` trafiają do `./output/<sprawa>/*.json`. Wynikowy JSON ma taką samą nazwę jak plik wejściowy. Ślady ekstrakcji (klasyfikacja, model, dowody dla pól) zapisują się w `./trace/`.

Wymagania: Python 3.13+, CPU (bez GPU), klucz do API zgodnego z OpenAI. `start.sh` / `start.bat` przy pierwszym uruchomieniu tworzą `.venv` i instalują `requirements.txt` (ok. 20 s, 210 MB, bez torch/CUDA). Model orientacji stron (ONNX, 7 MB) jest w repozytorium w `models/`, więc w trakcie pracy nic się nie pobiera.

### Przetwarzanie wsadowe

- Dokumenty spoza trzech typów dostają plik z pustym JSON-em `{}`.
- Każdy JSON zapisuje się od razu po przetworzeniu dokumentu. Po przerwaniu (Ctrl+C, awaria) ponowne `./start.sh` pomija dokumenty z gotowym wynikiem i dokańcza resztę. `--force` przetwarza wszystko od nowa.
- Błąd jednego dokumentu nie zatrzymuje partii: dokument dostaje wynik zastępczy (szkielet typu rozpoznanego regułami albo `{}`), błąd trafia do `trace/` i do podsumowania, a ponowne uruchomienie próbuje go jeszcze raz.
- Zły klucz API (HTTP 401) lub brak środków (402) przerywa partię od razu z czytelnym komunikatem (kod wyjścia 2). Gotowe dokumenty zostają, po poprawce wystarczy uruchomić ponownie.
- Limity dostawcy: wszystkie zapytania (LLM i OCR, ze wszystkich dokumentów) przechodzą przez wspólny limit `llm.max_concurrency` (16). Błędy 429/5xx, timeouty i zerwane połączenia są ponawiane z wykładniczym backoffem z jitterem i respektowaniem `Retry-After`. Po 429 wszystkie wątki czekają razem, zamiast zasypywać dostawcę (`o2j/api.py`).
- Na końcu drukuje się podsumowanie: liczba dokumentów, dokumenty spoza puli i z błędem, czas, dok./min, liczba wywołań LLM, koszt, ponowienia.
- Równoległość: `--workers N` (domyślnie 8, `run.workers` w `config/settings.yaml`). Praca to głównie czekanie na API, więc 8 wątków wystarcza także na 2 rdzeniach.

Pomiar (profil `auto`, domyślne 8 wątków, few-shot bez przykładów z własnej sprawy):

| | 150 PDF, `./start.sh` (MacBook) | 42 PDF, w tym 24 skany (Docker `--cpus 2 --memory 2g`) | te same 42 PDF (Docker `--cpus 1 --memory 1g`) |
|---|---|---|---|
| Czas całości | 96 s (96 dok./min) | 153 s (16.5 dok./min) | 227 s (11.1 dok./min) |
| Szczyt pamięci | 425 MB RSS | 836 MB cgroup (z cache plików) | 327 MB RSS, 406 MB cgroup |
| CPU | 7 s na 96 s | 24 s na 153 s | 25 s na 227 s |
| Wywołania LLM / koszt | 221 / $0.10 | 89 / $0.05 | 96 / $0.06 |
| F1 | 0.9993 | 0.9976 | 1.0000 |

Zestaw 150 PDF: 44 sprawy z `data/train`, 8 dokumentów negatywnych, 6 skanów z `samples/`. Zestaw 42 PDF: skany z `data/scans` i `data/hard_scans/faded` (lokalny zestaw, poza repozytorium), 5 spraw cyfrowych, 3 negatywne. Czas zależy głównie od API: skan to ok. 20-75 s (OCR 8B), dokument cyfrowy 2-5 s. Nawet 150 samych skanów na 1 rdzeniu to szacunkowo ok. 15 min.

### Docker Compose

```bash
cp .env.example .env                      # klucz API
docker compose run --rm wrobelek          # ./input -> ./output (ślady w ./trace)
docker compose run --rm wrobelek --force  # opcje CLI jak w run.py
docker compose --profile gui up gui       # GUI na http://127.0.0.1:8000
```

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

Działa z każdym API zgodnym z OpenAI, które serwuje model o otwartych wagach. Konfiguracja jest w `.env` / `config/settings.yaml`. Domyślny profil `auto` używa modeli Mistral AI hostowanych w UE (przez OpenRouter z przypięciem dostawcy): Ministral 3B do ekstrakcji dokumentów cyfrowych, Ministral 8B do klasyfikacji niepewnych dokumentów, OCR skanów i eskalacji. `O2J_LLM_MODEL` z `.env` jest modelem bazowym dla profili, które go nie nadpisują.

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
