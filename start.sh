#!/usr/bin/env sh
# Odwolania2JSON: przetwarza ./input -> ./output (ślady ekstrakcji w ./trace)
# Użycie: ./start.sh [--profile deterministyczny|ekonomiczny|standard|auto|maksymalny] [--input X --output Y] [--force]
# Ponowne uruchomienie pomija dokumenty, które mają już wynik (--force przetwarza wszystko od nowa).
cd "$(dirname "$0")" || exit 1
if [ ! -f .venv/.o2j_installed ]; then
  PY=""
  for c in python3.13 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)'; then PY="$c"; break; fi
  done
  [ -z "$PY" ] && { echo "Wymagany Python 3.13+"; exit 1; }
  echo "Tworzę środowisko .venv ($PY) i instaluję zależności..."
  [ -x .venv/bin/python ] || "$PY" -m venv .venv || exit 1
  .venv/bin/python -m pip install -q --upgrade pip && .venv/bin/python -m pip install -q -r requirements.txt || exit 1
  touch .venv/.o2j_installed
fi
[ -f .env ] || [ -n "$O2J_LLM_API_KEY" ] || echo "UWAGA: brak pliku .env — skopiuj .env.example do .env i wpisz klucz API."
exec .venv/bin/python run.py "$@"
