@echo off
setlocal EnableDelayedExpansion
REM Odwolania2JSON - interfejs w przegladarce: http://127.0.0.1:8000
cd /d "%~dp0"
if not exist ".venv\.o2j_installed" (
  set "PY="
  py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
  if not defined PY (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=py -3"
  )
  if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
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
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || exit /b 1
  echo ok> ".venv\.o2j_installed"
)
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" gui.py
