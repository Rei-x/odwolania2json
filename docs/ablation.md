# Ablacja kroków pipeline

Skrypt: `eval/ablation.py`. Działa wyłącznie przez nadpisania ustawień i monkeypatche, kod produkcyjny jest bez zmian.
Surowe wyniki: `docs/ablation.json`. Przebieg z 2026-11-21, po jednym przebiegu na szczebel.

Dane:
- **Train subset**: te same 12 folderów co w `eval/bench_models.py`, czyli 33 dokumenty w zakresie i 13 spoza zakresu.
- **Blind**: zamrożony zestaw, 60 dokumentów w zakresie i 3 spoza. Podajemy tylko wynik zagregowany.

Model: Ministral 8B (profil `standard`, Mistral EU przez OpenRouter). Wyjątek to szczebel g, który używa profilu `auto`.
Drabinka jest kumulacyjna: każdy szczebel zawiera wszystkie poprzednie.

| szczebel | co dochodzi | F1 train | Δ | F1 blind | Δ | negatywy blind | koszt train + blind | czas train / blind |
|---|---|---|---|---|---|---|---|---|
| a | tekst strony + jedno wywołanie LLM z JSON Schema; typ wybiera LLM spośród 3 typów (bez reguł, bez `inny`) | 0.9136 | – | 0.9357 | – | 0/3 | $0.038 + $0.038 | 155 s / 55 s |
| b | + głosowanie reguły/LLM przy klasyfikacji, dokument spoza zakresu → `{}` | 0.9600 | +0.046 | 0.9459 | +0.010 | 3/3 | $0.019 + $0.027 | 30 s / 34 s |
| c | + few-shot (2 najbliższe dokumenty treningowe) | 0.9864 | +0.026 | 0.9821 | +0.036 | 3/3 | $0.029 + $0.053 | 57 s / 101 s |
| d | + normalizacja deterministyczna (normalizatory z YAML) | 0.9823 | −0.004 | 0.9837 | +0.002 | 3/3 | $0.012 + $0.024 | 34 s / 41 s |
| e | + `snap_to_text` i `rules_fill` | 0.9973 | +0.015 | 0.9822 | −0.002 | 3/3 | $0.011 + $0.023 | 63 s / 47 s |
| f | + pętla weryfikacja → naprawa (`max_rounds: 2`), czyli pełny `standard` | 0.9973 | 0.000 | 0.9822 | 0.000 | 3/3 | $0.013 + $0.019 | 36 s / 52 s |
| g | + router/eskalacja (profil `auto`: reguły + 3B, trudne dokumenty → 8B) | 0.9973 | 0.000 | 0.9822 | 0.000 | 3/3 | $0.027 + $0.058 | 50 s / 73 s |

Czas to czas ściany całego przebiegu przy 8 wątkach: 46 dokumentów w train, 63 w blind.
Koszt drabinki: $0.392.

Jak to czytać:
- Od a do g F1 rośnie o +0.084 na train i +0.047 na blind. Najwięcej dają klasyfikacja z odrzucaniem dokumentów spoza zakresu (b) i few-shot (c).
- Na szczeblu a 13 negatywów z train jest zmuszonych do jednego z trzech typów i dostaje ekstrakcję, co daje FP. Na blind to 0/3 odrzuconych.
- Normalizacja (d) i `snap_to_text`/`rules_fill` (e) poprawiają głównie zapis (IBAN bez `PL`, `BZP` bez spacji, daty). Na blind ich wpływ mieści się w szumie.
- Szum między przebiegami tej samej konfiguracji: pełny `standard` dał na blind 0.9822 tutaj i 0.9845 w `docs/bench_parsers.json`, a na train 0.9973 i 0.9946.
  Różnice rzędu ±0.003 nie są więc istotne. Dotyczy to spadku −0.004 na d (train) i zerowych przyrostów f/g.
- Na tym subsecie f i g nie zmieniają F1. Weryfikacja i router działają na dokumentach, które sprawiają kłopot.
  Takich prawie tu nie ma: po e na train zostają 2 błędne pola (FP) na 374.
- Czasy rungów są głównie czasem odpowiedzi API i różnią się między przebiegami. Szczebel a był wolny (155 s) z powodu kolejki u dostawcy,
  nie z powodu pracy lokalnej.

Na każdym szczeblu włączone są elementy, które są częścią samego wywołania ekstrakcji:
- nasz prompt systemowy z opisem pól,
- constrained decoding po JSON Schema,
- dopasowanie wyniku do schematu i enumów,
- pola pochodne (`czynnosc_opis` z `czynnosc_powod_id`),
- ponowienie przy pustym wyniku,
- kontrole na poziomie sprawy.

Wersja bez naszego promptu i bez schematu domenowego jest w `docs/bench_parsers.md` jako „typowe podejście”.

## Orientacja skanów (`doc_ori`)

Zbiór `data/hard_scans/rotated_90`: 5 spraw, strony obrócone o 90°. Profil `standard`, OCR modelem wizyjnym (Ministral 8B).
Jedyna zmiana między przebiegami to `ocr.preprocess`.

| wariant | F1 | koszt |
|---|---|---|
| `doc_ori` włączone (domyślnie) | **0.9704** | $0.031 |
| `doc_ori` wyłączone | 0.8952 | $0.036 |

Wyłączenie orientacji obniża F1 o 0.075. Czasy (576 s vs 265 s) nie są porównywalne: przebieg z `doc_ori` szedł równolegle
z innymi wywołaniami API.

## Odtworzenie

```bash
.venv/bin/python -m eval.ablation run --rungs a b c d e f g --blind --budget 1.0
.venv/bin/python -m eval.ablation scan --src data/hard_scans/rotated_90
```
