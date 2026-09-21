@echo off
REM One-click local start for JobPilot on Windows.
setlocal

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt

echo Starting JobPilot at http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
uvicorn app.main:app --host 127.0.0.1 --port 8000
