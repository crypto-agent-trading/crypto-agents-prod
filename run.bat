@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ==================================================================
REM  Crypto Agents Pro - Windows launcher
REM  Usage:  run.bat [paper|live] [PORT] [rest|ws] [--no-browser]
REM          run.bat            -> paper, :8000, rest
REM          run.bat live 8000 ws
REM ==================================================================

set MODE_ARG=%1
set PORT_ARG=%2
set FEED_ARG=%3
set NO_BROWSER=%4

if "%MODE_ARG%"=="" set MODE_ARG=paper
if /I "%MODE_ARG%"=="live" (set MODE=live) else (set MODE=paper)

if "%PORT_ARG%"=="" (set PORT=8000) else (set PORT=%PORT_ARG%)

if /I "%FEED_ARG%"=="ws" (set FEED_MODE=ws) else (set FEED_MODE=rest)

echo.
echo ================== Crypto Agents Pro Launcher ==================
echo   MODE        = %MODE%
echo   PORT        = %PORT%
echo   FEED_MODE   = %FEED_MODE%
echo   PYTHONPATH  = (repo root)
echo ================================================================
echo.

REM --- Check Python ---
where python >NUL 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.11+ and retry.
  exit /b 1
)

REM --- Create venv if missing ---
if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating virtual environment .venv
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )
)

REM --- Upgrade pip & install deps ---
echo [SETUP] Upgrading pip and installing requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip >NUL
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install requirements.
  exit /b 1
)

REM --- Ensure .env exists ---
if not exist ".env" (
  if exist ".env.example" (
    echo [SETUP] Creating .env from .env.example
    copy /Y ".env.example" ".env" >NUL
  ) else (
    echo [WARN] No .env or .env.example found. The app will use defaults.
  )
)

REM --- Optional: open UI in browser ---
if /I not "%NO_BROWSER%"=="--no-browser" (
  echo [INFO] Opening http://localhost:%PORT%/ui/ in your browser...
  REM small delay so uvicorn starts listening
  powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:%PORT%/ui/'" 2>NUL
)

REM --- Set runtime env (overrides .env for this session only) ---
set PYTHONPATH=%cd%
set LOG_LEVEL=INFO
REM MODE & FEED_MODE are read by pydantic settings; env overrides .env
set MODE=%MODE%
set FEED_MODE=%FEED_MODE%

echo.
echo [RUN] Starting API:  http://localhost:%PORT%  (CTRL+C to stop)
echo       UI:            http://localhost:%PORT%/ui/
echo       Docs:          http://localhost:%PORT%/docs
echo       Metrics:       http://localhost:%PORT%/metrics
echo.
".venv\Scripts\python.exe" -m uvicorn app.api.main:app --host 0.0.0.0 --port %PORT%
