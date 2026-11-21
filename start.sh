#!/usr/bin/env sh
# Odwolania2JSON: przetwarza ./input -> ./output (ślady ekstrakcji w ./trace)
# Użycie: ./start.sh [--profile deterministyczny|ekonomiczny|standard|auto|maksymalny] [--input X --output Y]
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  PY=""
  for c in python3.13 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)'; then PY="$c"; break; fi
  done
  [ -z "$PY" ] && { echo "Wymagany Python 3.13+"; exit 1; }
  "$PY" -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt || exit 1
fi
exec .venv/bin/python run.py "$@"
