#!/usr/bin/env bash
# Przygotowanie serwera oceny (Ubuntu 24.04, Docker + Compose v2). Uruchomić w /opt/solution po skopiowaniu projektu.
#   bash deploy/vm/setup.sh
set -euo pipefail
cd /opt/solution
[ -f .env ] || { echo "Brak /opt/solution/.env (skopiuj .env.example i wpisz klucz API)"; exit 1; }
grep -q '^O2J_LLM_API_KEY=.\+' .env || { echo "W .env brakuje O2J_LLM_API_KEY"; exit 1; }
mkdir -p input output trace gui_data
echo "== budowanie obrazu (raz, przed oceną)"
docker compose build
echo "== GUI w tle na porcie 8000 (restart: unless-stopped)"
docker compose -f docker-compose.yml -f deploy/vm/gui.override.yml --profile gui up -d gui
echo "== test na przykładzie (input/_smoke, potem sprzątanie)"
mkdir -p input/_smoke
cp tests/fixtures/smoke/*.pdf input/_smoke/ 2>/dev/null || true
if ls input/_smoke/*.pdf >/dev/null 2>&1; then
  docker compose run --rm wrobelek --force --profile standard
  ls -la output/_smoke
  sudo rm -rf input/_smoke output/_smoke trace/_smoke   # wyniki z kontenera należą do roota
fi
echo "OK. Komenda oceny (RUN.md): docker compose run --rm wrobelek --force --profile standard"
