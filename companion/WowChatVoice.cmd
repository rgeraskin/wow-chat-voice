@echo off
rem WoW Chat Voice: starts WoW through Battle.net, reads chat lines from the addon's strip and speaks them.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto :run
echo Creating the Python environment...
python -m venv .venv || goto :fail
.venv\Scripts\python.exe -m pip install -q -r requirements.txt || goto :fail
echo Installing F5-TTS: race voices, NVIDIA GPU, several GB...
.venv\Scripts\python.exe -m pip install -q -r requirements-f5.txt || echo F5-TTS not installed: Windows voices only.
:run
title WoW Chat Voice
.venv\Scripts\python.exe -m wcv
if errorlevel 1 pause
exit /b
:fail
echo Setup failed.
pause
