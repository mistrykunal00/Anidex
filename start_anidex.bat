@echo off
setlocal
cd /d "%~dp0"
py -m http.server 8000
