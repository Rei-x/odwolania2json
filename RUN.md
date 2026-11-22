# Wróbelek (Odwołania2JSON) — uruchomienie oceny

## Komenda

Uruchomić z katalogu `/opt/solution` (bez interakcji, kończy się sama):

```bash
docker compose run --rm wrobelek --force
```

- Przetwarza wszystkie pliki z `/opt/solution/input/<sprawa>/*.pdf` i zapisuje `/opt/solution/output/<sprawa>/<ta sama nazwa>.json`.
- Dokumenty spoza trzech typów (odwołanie, pełnomocnictwo, potwierdzenie przelewu) dostają pusty JSON `{}`.
- Na końcu wypisuje podsumowanie (liczba dokumentów, czas, błędy). Ślady przetwarzania: `/opt/solution/trace/`.
- `--force` przetwarza wszystko od nowa, nawet gdy w `output/` są już wyniki z poprzedniego uruchomienia.
- Obraz Dockera (`odwolania2json:latest`) jest zbudowany na serwerze wcześniej; komenda niczego nie pobiera.

Czas: zmierzone na tym serwerze (2 vCPU): 226 PDF (przykłady UZP + 30 skanów) w 2 min 52 s, 0 błędów; 150 PDF mieści się z dużym zapasem w 45 min.

## Usługi zewnętrzne i klucze

Klucz API jest w `/opt/solution/.env` (`O2J_LLM_API_KEY`, adres w `O2J_LLM_BASE_URL`).

- **LLM:** otwarte modele Mistral AI **Ministral 3B i Ministral 8B** (profil `auto`: reguły + Ministral 3B, trudne dokumenty i skany od razu Ministral 8B), przez API zgodne z OpenAI: OpenRouter, regionalny endpoint UE `https://eu.openrouter.ai/api/v1` (inferencja wyłącznie u dostawców w Unii Europejskiej, routing przypięty do Mistral AI, `data_collection: deny`, umowa powierzenia przetwarzania danych zaakceptowana).
- **OCR skanów:** Ministral 8B (model wizyjny) przez to samo API; tekst z PDF-ów cyfrowych czytany lokalnie.
- **Lokalnie (CPU, bez GPU):** pypdfium2 (warstwa tekstowa PDF), PP-LCNet ONNX (orientacja stron 0/90/180/270), reguły z plików YAML w `config/doctypes/`.

## GUI (dodatkowo)

Interfejs webowy działa w tle na porcie 8000: `http://<adres-serwera>:8000` (kontener `gui`, startuje sam po restarcie).
Ten sam interfejs publicznie: https://wrobelek.suzuya.dev
