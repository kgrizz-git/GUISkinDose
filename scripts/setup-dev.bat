@echo off
setlocal enabledelayedexpansion

where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] uv not found; the locked git hooks require uv.
    echo Install uv, then run: uv sync --extra dev --extra gui --locked
    exit /b 1
)

where pre-commit >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pre-commit not found.
    echo Activate your venv or install dependencies first:
    echo   pip install -e ".[dev,gui]"
    exit /b 1
)

call pre-commit install
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call pre-commit install --hook-type pre-push
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call pre-commit install --hook-type commit-msg
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
echo Git hooks installed (pre-commit + pre-push + commit-msg).
echo For routed privacy changes, run: python scripts/privacy_admission.py run --mode staged
