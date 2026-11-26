@echo off
title E-Commerce CS Agent
cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] backend\venv not found. Please install dependencies first.
  pause
  exit /b 1
)
venv\Scripts\python.exe run_server.py
pause
