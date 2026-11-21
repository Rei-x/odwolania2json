# Parsery: nasz tekst (pypdfium2) vs Docling vs Unstructured

Skrypt: `eval/bench_parsers.py` (tylko ewaluacja, kod produkcyjny bez zmian). Surowe wyniki: `docs/bench_parsers.json`.
Data przebiegu: 2026-11-21. Wszystkie liczby poniżej pochodzą z przebiegów opisanych w tym pliku.

## Co porównujemy

1. **Podmiana parsera w naszym pipeline.** Ten sam profil, model, prompty, few-shot, normalizacja,
   weryfikacja i scorer. Zmienia się tylko warstwa tekstu: `o2j.pdf.load` jest podmieniane (monkeypatch)
   na loader, który zwraca tekst stron z Docling / Unstructured. Teksty przykładów few-shot też idą
   przez podmieniony parser, więc przykład i dokument mają ten sam format.
2. **„Typowe podejście”.** Tekst z parsera + jedno zwykłe wywołanie LLM: szablon organizatora
   (`data/schemas/*.json` + słownik powodów) jako jedyna instrukcja, JSON Schema tylko dla kształtu.
   Bez few-shot, normalizacji, reguł, weryfikacji i kontroli sprawy. Ten sam model (Ministral 8B, Mistral EU).
   Baseline dostaje **prawdziwy typ dokumentu za darmo** (oracle) i liczony jest tylko na dokumentach
   w zakresie, co go faworyzuje.
3. **Szybkość** parsowania (zimny start i rozgrzany) oraz end-to-end.
4. **Opus jako referencja**: Claude Opus 5.5 przez Anthropic API (nie OpenRouter), czyta PDF
   natywnie, dostaje tylko szablon organizatora (`eval/opus_reference.annotate`), typ dokumentu oracle.

Konfiguracja parserów:

| parser | wersja | ustawienia |
|---|---|---|
| nasz (`pdfium`) | pypdfium2 5.x | `o2j.pdf.load`: warstwa tekstu, spłaszczenie adnotacji, naprawa mojibake; bez OCR (PDF-y cyfrowe) |
| Docling | docling 2.151.1 | `DocumentConverter` z domyślnymi opcjami (model układu, struktura tabel, OCR auto → RapidOCR dla bitmap), wymuszone `device=cpu`, 4 wątki, `export_to_markdown(page_no=i)` |
| Unstructured fast | unstructured 0.27.37 | `partition_pdf(strategy="fast", languages=["pol"])`, elementy łączone per strona |
| Unstructured hi_res | unstructured 0.27.37 + unstructured-inference 1.6.17 | `strategy="hi_res"`, model układu YOLOX na onnxruntime CPU, Tesseract 5 z `pol.traineddata` (tessdata_fast) |

Docling i Unstructured są zainstalowane w osobnym `.venv-bench` (1,5 GB, torch 2.15); produkcyjne
`.venv` i `requirements.txt` bez zmian.

## Dane

- **Train subset**: te same 12 folderów co w `eval/bench_models.py` (`negatywne` + przyklad_05, 10, …, 55):
  33 dokumenty w zakresie + 13 spoza zakresu (46 PDF, 212 stron).
- **Blind**: zamrożony `data/blind` (20 spraw, 60 dokumentów w zakresie + 3 negatywy). Raportujemy tylko
  zagregowane F1; wyjścia per dokument są kasowane.
- Scorer: `eval/score.py` (reguły organizatora). Negatyw poprawnie odrzucony nie dodaje nic do F1;
  błędnie wyekstrahowany dodaje FP.

## Sprzęt

- **Lokalnie**: Apple M5 Pro (18 rdzeni), 64 GB RAM, macOS 26.6.2. Docling wymuszony na CPU, onnxruntime
  w Unstructured hi_res na CPUExecutionProvider. GPU/MPS nieużywane.
- **Hetzner ccx23**: AMD EPYC-Milan, 4 dedykowane vCPU, 16 GB RAM, bez GPU, osobny venv
  (`/root/bench_parsers/.venv`). W tle chodził sweep modeli (głównie czekanie na API, load ~0,1).

## Wyniki

**Uwaga: przebiegi z Ministral 8B na tekście z Docling / Unstructured (pozycje 1 i 2) NIE zostały wykonane.**
Konto OpenRouter skończyło środki (HTTP 402) w trakcie benchmarku. Wykonano je tylko dla naszego parsera.
Komórki „czeka” uzupełnimy po doładowaniu (komendy na dole). Wszystkie pozostałe liczby pochodzą z faktycznych przebiegów.

### F1 i koszt (profil `standard`, Ministral 8B, o ile nie podano inaczej)

| setup | parser | F1 train subset | F1 blind | koszt train + blind | czas/dok (mediana) |
|---|---|---|---|---|---|
| nasz pipeline (`standard`) | nasz | **0.9973** | **0.9845** (negatywy 3/3) | $0.039 + $0.068 | 3.9 s e2e (train, 8 równolegle) |
| nasz pipeline (`standard`) | Docling | czeka | czeka | – | parsowanie +0.59 s |
| nasz pipeline (`standard`) | Unstructured fast | czeka | czeka | – | parsowanie +0.03 s |
| nasz pipeline (`standard`) | Unstructured hi_res | czeka | czeka | – | parsowanie +1.7 s |
| „typowe podejście”: tekst + 1 wywołanie LLM* | nasz | 0.9556 | 0.9331 | $0.009 + $0.020 | 2.7 s / 2.4 s |
| „typowe podejście”* | Docling / Unstructured | czeka | czeka | – | – |
| tylko reguły (`deterministyczny`), bez LLM | nasz | 1.0000** | 0.8159 (3/3) | $0 | 0.005 s; 66 dok/s na 1 wątku |
| tylko reguły | Docling | 0.6595 | 0.6299 (2/3) | $0 | – |
| tylko reguły | Unstructured fast | 0.9582 | 0.8000 (2/3) | $0 | – |
| tylko reguły | Unstructured hi_res | 0.9568 | 0.7913 (2/3) | $0 | – |
| Claude Opus 5.5 (Anthropic API, PDF natywnie, effort high)* | – | 1.0000 | 1.0000 | $0.95 + $1.99 | 3.7 s / 4.0 s |

\* Typ dokumentu podany z góry (oracle), liczone tylko na dokumentach w zakresie (33 train, 60 blind).
Nasz pipeline sam klasyfikuje i odrzuca negatywy. Ponieważ poprawnie odrzucony negatyw nic nie dodaje do F1,
liczby są porównywalne, ale baseline i Opus mają łatwiej.
\*\* Reguły pisaliśmy na danych treningowych, więc 1.0 na train jest optymistyczne. Miarodajny jest blind.

Wiersze „tylko reguły” z Docling/Unstructured mierzą głównie to, że nasze reguły pisano pod układ tekstu
pypdfium2 (markdown z `##`, tabelami i rozbitymi liniami nie pasuje do wzorców). To nie jest ocena jakości
tych parserów, tylko pokazuje, że warstwy tekstu nie da się podmienić bez kosztów.

Wydatki: OpenRouter $0.136 (z limitu $1.5), Opus $2.94 (z limitu $5).

### Czas parsowania (train subset: 46 PDF, 212 stron, jeden proces, sekwencyjnie)

| parser | maszyna | zimny start (import + init + 1. dok.) | rozgrzany: mediana / dok | rozgrzany: s / stronę |
|---|---|---|---|---|
| nasz (pypdfium2) | M5 Pro | 0.02 s | 0.001 s | 0.002 |
| Docling | M5 Pro | 10.8 s (1.3 + 2.4 + 7.1) | 0.59 s | 0.34 |
| Unstructured fast | M5 Pro | 2.6 s (2.3 + 0 + 0.3) | 0.031 s | 0.031 |
| Unstructured hi_res | M5 Pro | 9.8 s (1.8 + 1.0 + 7.1) | 1.71 s | 1.67 |
| nasz (pypdfium2) | Hetzner ccx23 | 0.07 s | 0.002 s | 0.003 |
| Docling | Hetzner ccx23 | 45.2 s (5.5 + 12.6 + 27.1) | 2.22 s | 1.80 |
| Unstructured fast | Hetzner ccx23 | 3.8 s | 0.065 s | 0.075 |

Zimny start = nowy proces, modele już na dysku (pobranie modeli przy pierwszym uruchomieniu w ogóle,
ok. 100 s dla Docling, nie jest wliczone). Na Hetznerze pierwszy dokument Docling (27 s) mógł jeszcze
obejmować leniwe pobranie modeli OCR. Najwolniejsze są długie negatywy: 31-stronicowa broszura to w Docling 16 s na M5 Pro
i 111 s na Hetznerze; 35-stronicowy dokument w hi_res to 46 s na M5 Pro. Na Hetznerze nie mierzyliśmy hi_res (brak `pol.traineddata`).

End-to-end dla podmienionego parsera = opóźnienie pipeline na tym tekście + czas parsowania tego dokumentu.
Skrypt liczy to automatycznie (`e2e_median_s_per_doc`). Nasze 3.9 s/dok to mediana opóźnienia przy 8 równoległych
wątkach i w tym przebiegu zawiera klasyfikację, ekstrakcję, weryfikację i naprawę. Wcześniej cytowana mediana 2.7 s
pochodzi z innego przebiegu.

## Przykłady błędów parserów (z danych treningowych / wariantów)

1. **Docling gubi datę pisma.** Docling uznaje pierwszą linię („Lublin, dnia 9 listopada 2026 roku”) za nagłówek
   strony (furniture) i nie ma jej w eksporcie markdown. W 15 z 45 odwołań treningowych z polem
   `OdwolanieKIO.data` w gold data w ogóle nie występuje w tekście Docling (np. przyklad_03, 05, 06, 08, 16, 21, 26, 30).
   W tekście pypdfium2 i Unstructured jest zawsze. Tego pola żaden LLM już nie odtworzy.
2. **Docling miesza adresata z Odwołującym.** `data/train/przyklad_05/odwolanie.pdf`: pod nagłówkiem
   `## Odwołujący:` Docling stawia najpierw „Prezes Krajowej Izby Odwoławczej ul. Postępu 17A 02-676 Warszawa”,
   a dopiero potem firmę Odwołującego. Model widzi adres KIO jako pierwszy podmiot w sekcji Odwołującego.
3. **Dwie kolumny „Odwołujący | Zamawiający”** (`data/variants/przyklad_12_pesel_multi_pel/odwolanie.pdf`, `przyklad_15_act_in_zarzuty`):
   - Unstructured (fast i hi_res) zwraca komórki na przemian: „Odwołujący / Zamawiający / Wexford Usługi sp. j. /
     Lunareth Sieci S.A. / KRS: 9990299642 / KRS: 9992132121 / …”. Nazwy i numery są oddzielone od ról i przeplatane;
     to, że co drugi KRS należy do Zamawiającego, wynika tylko z kolejności.
   - **Nasz pypdfium2 też czyta wierszami**: „Wexford Usługi sp. j. Lunareth Sieci S.A.”, „KRS: 9990299642 KRS: 9992132121”.
     Skargę jury można więc odnieść także do naszej surowej warstwy tekstu. U nas problem rozwiązują kolejne kroki
     (few-shot z takimi układami, reguły, weryfikacja), nie parser.
   - Docling ten przypadek rozpoznaje poprawnie i robi z niego tabelę markdown z kolumnami `Odwołujący | Zamawiający`.
     Na tych samych stronach gubi jednak datę i miejscowość z nagłówka (przyklad_15: „Poznań, dnia dwunastego stycznia 2026 r.”).
4. **Interpunkcja i warianty zapisu** (z „typowego podejścia” na naszym tekście, train subset; to pokazuje rolę normalizacji,
   a nie parsera): rachunki z prefiksem `PL…` zamiast samych cyfr (9× `przelew_bankowy.na_rachunek`, 9× `z_rachunku`),
   `2026/BZP 00999412` ze spacją, dwóch pełnomocników sklejonych w jedno `imie_nazwisko` („Magdalena Wróblewska, Tomasz Kędzierski”),
   literówka w mailu (`sekreciat@…`), ucięte cyfry rachunku, zły `czynnosc_powod_id` (11 zamiast 4).
5. **Wierność tekstu (train, wszystkie PDF):** średnio Docling odtwarza 97–98% słów z warstwy tekstowej,
   Unstructured fast 98–99%. Docling gubi też daty wydruku w stopkach potwierdzeń przelewu (np. „Wydrukowano: 07-07-2026”).
   Nie są to pola gold, ale pokazuje to, że stopki i nagłówki są wycinane.

## Co nie zadziałało / ograniczenia

- **Brak przebiegów Ministral dla Docling/Unstructured** (pipeline i baseline, train i blind): OpenRouter 402.
  Cache tekstów jest gotowy (`runs/bench_parsers/cache/`) dla Docling i Unstructured fast (cały train + blind).
  Dla hi_res jest tylko blind + train subset; przed przebiegiem pipeline (few-shot czyta cały train) trzeba
  dokończyć `parse --parser unstructured_hires`. To ok. 20–30 min na M5 Pro, bo długie negatywy zajmują po 20–60 s.
- Ablacja kroków (`eval/ablation.py`, `docs/ablation.md`) jest gotowa, ale nie uruchomiona z tego samego powodu.
- Na train subset Opus i nasz pipeline mają prawie sufit (0.997–1.0). Różnice widać dopiero na blind.
- Jeden przebieg na setup (temperatura 0, ale dostawca nie jest w pełni deterministyczny). Nasz `standard`
  na train dał teraz 0.9973, a w `docs/bench_sweep.json` 0.9946. Blind 0.9845 vs cytowane 0.9815.
- Czasy zapisane w cache pochodzą z przebiegu równoległego z innymi zadaniami, a liczy z nich e2e
  dla podmienionych parserów. Tabela czasów pochodzi z osobnego, czystego przebiegu `timing`.
- hi_res na macOS: onnxruntime ma CoreML, ale unstructured-inference wybiera tylko TensorRT/CUDA/CPU, więc liczy na CPU.
  Docling ma wymuszone CPU (domyślnie `auto` wybrałby MPS).
- Unstructured hi_res wymagał doinstalowania `pol.traineddata` (tessdata_fast) do lokalnego katalogu
  `runs/bench_parsers/tessdata` (`TESSDATA_PREFIX`). Systemowy Tesseract ma tylko eng/osd.

## Jak odtworzyć

```bash
uv venv .venv-bench --python 3.13
uv pip install --python .venv-bench/bin/python docling "unstructured[pdf]" pypdfium2
export TESSDATA_PREFIX=$PWD/runs/bench_parsers/tessdata   # eng/osd + pol.traineddata (tessdata_fast)
for p in docling unstructured_fast unstructured_hires; do .venv-bench/bin/python -m eval.bench_parsers parse --parser $p; done
for p in pdfium docling unstructured_fast unstructured_hires; do .venv-bench/bin/python -m eval.bench_parsers timing --parser $p --machine m5pro; done
for p in pdfium docling unstructured_fast unstructured_hires; do for s in train blind; do
  .venv/bin/python -m eval.bench_parsers pipeline --parser $p --set $s            # profil standard
  .venv/bin/python -m eval.bench_parsers pipeline --parser $p --set $s --profile deterministyczny
  .venv/bin/python -m eval.bench_parsers baseline --parser $p --set $s
done; done
.venv/bin/python -m eval.bench_parsers det
.venv/bin/python -m eval.bench_parsers opus --set train && .venv/bin/python -m eval.bench_parsers opus --set blind --spent <koszt z train>
```
