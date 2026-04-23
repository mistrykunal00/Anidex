$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
$env:ANIDEX_HTTPS = "1"
$env:ANIDEX_BIND_MODE = "lan"
py app.py
