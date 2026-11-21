@echo off
setlocal EnableDelayedExpansion
REM Odwolania2JSON: przetwarza .\input -> .\output (slady ekstrakcji w .\trace)
REM Uzycie: start.bat [--profile deterministyczny^|ekonomiczny^|standard^|auto^|maksymalny] [--input X --output Y] [--force]
REM Ponowne uruchomienie pomija dokumenty, ktore maja juz wynik (--force przetwarza wszystko od nowa).
cd /d "%~dp0"
if not exist ".venv\.o2j_installed" (
  set "PY="
  REM py launcher: najpierw 3.13, potem dowolny Python 3 w wersji 3.13 lub nowszej
  py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
  if not defined PY (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=py -3"
  )
  if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
  )
  if not defined PY (
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=python3"
  )
  if not defined PY (
    echo Wymagany Python 3.13+ ^(https://www.python.org/downloads/^). Zainstaluj go i uruchom ponownie.
    exit /b 1
  )
  echo Tworze srodowisko .venv ^(!PY!^) i instaluje zaleznosci...
  if not exist ".venv\Scripts\python.exe" (
    !PY! -m venv .venv || exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (
    echo Instalacja zaleznosci nie powiodla sie.
    exit /b 1
  )
  echo ok> ".venv\.o2j_installed"
)
if not exist ".env" if not defined O2J_LLM_API_KEY (
  echo UWAGA: brak pliku .env - skopiuj .env.example do .env i wpisz klucz API.
)
".venv\Scripts\python.exe" run.py %*
exit /b %ERRORLEVEL%
