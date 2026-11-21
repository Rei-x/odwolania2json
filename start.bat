@echo off
REM Odwolania2JSON: przetwarza .\input -> .\output (slady ekstrakcji w .\trace)
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
.venv\Scripts\python run.py %*
