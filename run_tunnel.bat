@echo off
cd /d %~dp0

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo cloudflared was not found on this PC.
    echo Install it on Windows with:
    echo   winget install --id Cloudflare.cloudflared
    echo Then run this file again.
    pause
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo Missing virtual environment. Run:
    echo   py -m venv .venv
    echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

set ANIDEX_BIND_MODE=loopback
start "Anidex Local Server" cmd /k ""%~dp0.venv\Scripts\python.exe" app.py"

echo Waiting for the local Flask server to respond...
powershell -NoProfile -Command ^
    "$ok = $false; for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health | Out-Null; $ok = $true; break } catch { Start-Sleep -Seconds 1 } }; if (-not $ok) { exit 1 }"
if errorlevel 1 (
    echo Flask did not start on http://127.0.0.1:5000.
    echo Check the Anidex Local Server window for the error.
    pause
    exit /b 1
)

echo.
echo Starting Cloudflare quick tunnel...
echo Keep this window open and copy the https://...trycloudflare.com URL.
echo.
cloudflared tunnel --url http://127.0.0.1:5000
pause
