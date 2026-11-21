#!/usr/bin/env sh
# Odwolania2JSON: przetwarza ./input -> ./output (ślady ekstrakcji w ./trace)
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python run.py "$@"
