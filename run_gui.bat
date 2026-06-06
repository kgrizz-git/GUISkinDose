@echo off
setlocal enabledelayedexpansion
title MyPySkinDose GUI Launcher

echo ==========================================
echo       MyPySkinDose GUI Launcher
echo ==========================================
echo.

:: Check for Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.10 or newer.
    pause
    exit /b 1
)

:: Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYTHON_VERSION=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if %PYTHON_MAJOR% LSS 3 (
    echo [ERROR] Python 3.10+ required. Found: %PYTHON_VERSION%
    pause
    exit /b 1
)

if %PYTHON_MAJOR% EQU 3 (
    if %PYTHON_MINOR% LSS 10 (
        echo [ERROR] Python 3.10+ required. Found: %PYTHON_VERSION%
        pause
        exit /b 1
    )
)

echo [OK] Python %PYTHON_VERSION% found

:: Determine which Python to use
set PYTHON_CMD=python

if exist .venv\Scripts\python.exe (
    set PYTHON_CMD=.venv\Scripts\python.exe
    echo [OK] Using .venv\Scripts\python.exe
) else if defined VIRTUAL_ENV (
    echo [OK] Using current virtual environment: %VIRTUAL_ENV%
) else (
    echo.
    echo [!] No virtual environment found.
    set /p create_venv="Would you like to create one at .venv? [Y/n]: "
    
    if /i "!create_venv!"=="n" (
        echo Proceeding without virtual environment...
    ) else (
        echo Creating virtual environment...
        python -m venv .venv
        if !ERRORLEVEL! NEQ 0 (
            echo [ERROR] Failed to create virtual environment.
            pause
            exit /b 1
        )
        echo [OK] Virtual environment created at .venv
        set PYTHON_CMD=.venv\Scripts\python.exe
    )
)

:: Check if package is installed
%PYTHON_CMD% -c "import mypyskindose" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] mypyskindose package is installed
    goto :run_gui
)

echo.
echo [!] mypyskindose package not installed.
echo Install options:
echo   [1] Core + GUI (browser mode)      - pip install -e ".[gui]"
echo   [2] Core + GUI + Native window     - pip install -e ".[gui-native]"
echo   [3] Skip (install manually later)
echo.

set /p install_choice="Select option [1/2/3, default=1]: "

if "%install_choice%"=="2" (
    echo Installing mypyskindose with GUI and native window support...
    %PYTHON_CMD% -m pip install -e ".[gui-native]"
) else if "%install_choice%"=="3" (
    echo Skipping. Install manually with: pip install -e ".[gui]"
) else (
    echo Installing mypyskindose with GUI...
    %PYTHON_CMD% -m pip install -e ".[gui]"
)

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo [OK] Installation complete

:run_gui
echo.
echo How would you like to run the GUI?
echo [1] Browser (Standard)
echo [2] Native Window (Requires pywebview)
echo.

set /p choice="Enter your choice (1 or 2, default is 1): "

if "%choice%"=="2" (
    :: Check for pywebview before launching native mode
    %PYTHON_CMD% -c "import webview" >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [!] pywebview not installed (required for native window mode).
        set /p install_pywebview="Would you like to install it? [Y/n]: "
        
        if /i "!install_pywebview!"=="n" (
            echo Switching to browser mode instead...
            set choice=1
        ) else (
            echo Installing pywebview...
            %PYTHON_CMD% -m pip install pywebview
            if !ERRORLEVEL! NEQ 0 (
                echo [ERROR] Failed to install pywebview.
                echo Switching to browser mode instead...
                set choice=1
            )
        )
    )
)

if "%choice%"=="2" (
    echo.
    echo Starting MyPySkinDose in Native Window mode...
    %PYTHON_CMD% -m mypyskindose --mode gui --native
) else (
    echo.
    echo Starting MyPySkinDose in Browser mode...
    %PYTHON_CMD% -m mypyskindose --mode gui
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] The application failed to start.
    echo Try installing dependencies: pip install -e ".[gui]"
    pause
)
