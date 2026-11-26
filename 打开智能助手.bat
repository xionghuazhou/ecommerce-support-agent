@echo off
title Open CS Agent
cd /d "%~dp0backend"

REM If server is not running, start it with a hidden console window
powershell -NoProfile -Command "$l = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if (-not $l) { Start-Process -FilePath '.\venv\Scripts\python.exe' -ArgumentList 'run_server.py' -WindowStyle Hidden }"

REM Wait until server is healthy (max ~15s), then open the chat page
powershell -NoProfile -Command "for ($i=0; $i -lt 30; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit } catch { Start-Sleep -Milliseconds 500 } }"

start "" "http://127.0.0.1:8000/"
exit
