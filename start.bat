@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %ERRORLEVEL%==0 (set PY=py) else (set PY=python)

%PY% -m venv .venv
call .\.venv\Scripts\activate.bat

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python app.py
