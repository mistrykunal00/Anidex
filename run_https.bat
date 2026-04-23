@echo off
cd /d %~dp0
set ANIDEX_HTTPS=1
set ANIDEX_BIND_MODE=lan
call .venv\Scripts\python.exe app.py
pause
