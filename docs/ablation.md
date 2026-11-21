# Ablacja kroków pipeline

**Status (2026-11-21): skrypt gotowy, przebiegi LLM jeszcze nie wykonane.** OpenRouter zwraca HTTP 402
(brak środków na koncie), więc żadna liczba F1 dla drabinki poniżej jeszcze nie istnieje. Tabela zostanie
uzupełniona z `docs/ablation.json` po pierwszym przebiegu.

Skrypt: `eval/ablation.py` (tylko nadpisania ustawień i monkeypatche, kod produkcyjny bez zmian).
Dane: te same 12 folderów treningowych co w `eval/bench_models.py` (33 dokumenty w zakresie + 13 spoza),
opcjonalnie zamrożony blind (tylko agregat). Model: Ministral 8B (profil `standard`), szczebel g: profil `auto`.

| szczebel | co dochodzi | F1 train | Δ | F1 blind | koszt | czas/dok |
|---|---|---|---|---|---|---|
| a | tekst strony + jedno wywołanie LLM z JSON Schema; typ wybiera LLM spośród 3 typów (bez reguł, bez `inny`) | – | – | – | – | – |
| b | + głosowanie reguły/LLM przy klasyfikacji, dokument spoza zakresu → `{}` | – | – | – | – | – |
| c | + przykłady few-shot (2 najbliższe dokumenty treningowe) | – | – | – | – | – |
| d | + normalizacja deterministyczna (normalizatory z YAML) | – | – | – | – | – |
| e | + `snap_to_text` i `rules_fill` | – | – | – | – | – |
| f | + pętla weryfikacja → naprawa (`max_rounds: 2`) = pełny `standard` | – | – | – | – | – |
| g | + router/eskalacja (profil `auto`: reguły + 3B, trudne dokumenty → 8B) | – | – | – | – | – |

Włączone na każdym szczeblu (część samego wywołania ekstrakcji): nasz prompt systemowy z opisem pól,
constrained decoding po JSON Schema, dopasowanie do schematu i enumów, pola pochodne
(`czynnosc_opis` z `czynnosc_powod_id`), ponowienie przy pustym wyniku, kontrole na poziomie sprawy.

Orientacja skanów (`doc_ori` on/off na `data/hard_scans/rotated_90`, profil `standard`): też czeka na środki
(OCR idzie przez model wizyjny po API).

```bash
.venv/bin/python -m eval.ablation run --rungs a b c d e f g --blind --budget 1.5
.venv/bin/python -m eval.ablation scan --src data/hard_scans/rotated_90
```
