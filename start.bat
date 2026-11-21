@echo off
setlocal EnableDelayedExpansion
REM Odwolania2JSON: przetwarza .\input -> .\output (slady ekstrakcji w .\trace)
REM Uzycie: start.bat [--profile deterministyczny^|ekonomiczny^|standard^|auto^|maksymalny] [--input X --output Y]
cd /d %~dp0
if not exist .venv (
  set "PY="
  py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
  if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
  )
  if not defined PY (
    echo Wymagany Python 3.13+ ^(https://www.python.org/downloads/^). Zainstaluj go i uruchom ponownie.
    exit /b 1
  )
  echo Tworze srodowisko i instaluje zaleznosci...
  !PY! -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt || exit /b 1
)
.venv\Scripts\python run.py %*
