#!/bin/bash
#
# GUISkinDose GUI Launcher for macOS/Linux
#
# USAGE:
#   1. Make this script executable (one-time setup):
#      chmod +x run_gui.sh
#
#   2. Run the script:
#      ./run_gui.sh
#
# REQUIREMENTS:
#   - Python 3.11+ with virtual environment at .venv (optional but recommended)
#   - Install dependencies: pip install -e ".[gui]"
#   - For native window mode: pip install -e ".[gui-native]"
#
# MODES:
#   [1] Browser mode - opens in your default web browser
#   [2] Native window mode - opens in a standalone desktop window (default)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "      GUISkinDose GUI Launcher"
echo "=========================================="
echo ""

# Parse and enforce the 3.11+ floor for $PYTHON_CMD; exits 1 on failure.
# Safe to call whenever PYTHON_CMD is (re-)selected. Rejects unreadable or
# non-numeric version output with the standard error (fail closed).
check_python_version() {
    if ! PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}'); then
        echo -e "${RED}[ERROR] Cannot run $PYTHON_CMD --version.${NC}"
        exit 1
    fi

    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if ! [[ "$PYTHON_MAJOR" =~ ^[0-9]+$ && "$PYTHON_MINOR" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}[ERROR] Could not determine Python version. Got: $PYTHON_VERSION${NC}"
        exit 1
    fi

    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
        echo -e "${RED}[ERROR] Python 3.11+ required. Found: $PYTHON_VERSION${NC}"
        exit 1
    fi
}

# Check for Python 3.11+
check_python() {
    # A pre-selected PYTHON_CMD (e.g. an existing .venv interpreter) takes
    # precedence: PATH may point at an older interpreter than the one in .venv.
    if [ -z "${PYTHON_CMD:-}" ]; then
        if command -v python3 &> /dev/null; then
            PYTHON_CMD="python3"
        elif command -v python &> /dev/null; then
            PYTHON_CMD="python"
        else
            echo -e "${RED}[ERROR] Python not found. Please install Python 3.11 or newer.${NC}"
            exit 1
        fi
    fi

    check_python_version

    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found"
}

# Check if running in a venv
in_venv() {
    if [ -n "$VIRTUAL_ENV" ]; then
        return 0
    fi
    return 1
}

# Offer to create venv if missing
setup_venv() {
    if [ -d ".venv" ]; then
        echo -e "${GREEN}✓${NC} Virtual environment found at .venv"
        return 0
    fi
    
    if in_venv; then
        echo -e "${GREEN}✓${NC} Already running in virtual environment: $VIRTUAL_ENV"
        return 0
    fi
    
    echo ""
    echo -e "${YELLOW}No virtual environment found.${NC}"
    read -r -p "Would you like to create one at .venv? [Y/n]: " create_venv
    
    if [[ "$create_venv" =~ ^[Nn]$ ]]; then
        echo "Proceeding without virtual environment..."
        return 1
    fi
    
    echo "Creating virtual environment..."
    if ! $PYTHON_CMD -m venv .venv; then
        echo -e "${RED}[ERROR] Failed to create virtual environment.${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✓${NC} Virtual environment created at .venv"
    return 0
}

# Check if package is installed
check_package_installed() {
    local PYTHON="$1"
    if $PYTHON -c "import guiskindose" 2>/dev/null; then
        return 0
    fi
    return 1
}

# Offer to install dependencies
setup_dependencies() {
    local PYTHON="$1"
    
    if check_package_installed "$PYTHON"; then
        echo -e "${GREEN}✓${NC} guiskindose package is installed"
        return 0
    fi
    
    echo ""
    echo -e "${YELLOW}guiskindose package not installed.${NC}"
    echo "Install options:"
    echo "  [1] Core + GUI (browser mode)      - pip install -e \".[gui]\""
    echo "  [2] Core + GUI + Native window     - pip install -e \".[gui-native]\""
    echo "  [3] Skip (install manually later)"
    echo ""
    read -r -p "Select option [1/2/3, default=1]: " install_choice
    
    local install_status=0
    case "$install_choice" in
        2)
            echo "Installing guiskindose with GUI and native window support..."
            $PYTHON -m pip install -e ".[gui-native]" || install_status=$?
            ;;
        3)
            echo "Skipping. Install manually with: $PYTHON -m pip install -e \".[gui]\" (or \".[gui-native]\" for native window mode)"
            return 3
            ;;
        *)
            echo "Installing guiskindose with GUI..."
            $PYTHON -m pip install -e ".[gui]" || install_status=$?
            ;;
    esac
    
    if [ "$install_status" -ne 0 ]; then
        echo -e "${RED}[ERROR] Installation failed.${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✓${NC} Installation complete"
    return 0
}

# Main setup checks
# Prefer an existing usable .venv interpreter so it is validated directly and
# never rejected over an older system Python on PATH.
if [ -x ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
fi
check_python

# Determine which Python to use
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo -e "${GREEN}✓${NC} Using .venv/bin/python"
elif in_venv; then
    PYTHON="$PYTHON_CMD"
    echo -e "${GREEN}✓${NC} Using current virtual environment"
else
    # setup_venv returns 1 on decline or creation failure; either way no
    # .venv was selected, so fall through to system Python (no set -e exit).
    if ! setup_venv; then
        echo "Continuing without a virtual environment."
    fi
    if [ -f ".venv/bin/python" ]; then
        PYTHON=".venv/bin/python"
    else
        PYTHON="$PYTHON_CMD"
    fi
fi

# Re-validate the selected interpreter as a final backstop (covers a freshly
# created or meanwhile-broken .venv binary).
PYTHON_CMD="$PYTHON"
check_python_version

echo -e "${GREEN}✓${NC} Selected interpreter: $PYTHON (Python $PYTHON_VERSION)"

# Check/install dependencies (skip-install exits 0 with a rerun hint, matching
# run_gui.bat; install failure exits 1; set -e safe via explicit handling).
if setup_dependencies "$PYTHON"; then
    dep_status=0
else
    dep_status=$?
fi

if [ "$dep_status" -eq 3 ]; then
    echo "Then rerun ./run_gui.sh."
    exit 0
elif [ "$dep_status" -ne 0 ]; then
    exit 1
fi

# Check if pywebview is installed (needed for native mode)
check_pywebview() {
    local PYTHON="$1"
    if $PYTHON -c "import webview" 2>/dev/null; then
        return 0
    fi
    return 1
}

# Offer to install pywebview for native mode
setup_pywebview() {
    local PYTHON="$1"
    
    echo ""
    echo -e "${YELLOW}pywebview not installed (required for native window mode).${NC}"
    read -r -p "Would you like to install it? [Y/n]: " install_pywebview
    
    if [[ "$install_pywebview" =~ ^[Nn]$ ]]; then
        echo "Switching to browser mode instead..."
        return 1
    fi
    
    echo "Installing pywebview..."
    if ! $PYTHON -m pip install pywebview; then
        echo -e "${RED}[ERROR] Failed to install pywebview.${NC}"
        echo "Switching to browser mode instead..."
        return 1
    fi
    
    echo -e "${GREEN}✓${NC} pywebview installed"
    return 0
}

# Ask for mode
echo ""
echo "How would you like to run the GUI?"
echo "[1] Browser (Standard)"
echo "[2] Native Window (Requires pywebview)"
echo ""
read -r -p "Enter your choice (1 or 2, default is 2): " choice
# Default to native window mode when no choice is entered.
choice="${choice:-2}"

if [ "$choice" == "2" ]; then
    # Check for pywebview before launching native mode
    if ! check_pywebview "$PYTHON"; then
        if ! setup_pywebview "$PYTHON"; then
            # User declined or install failed, fall back to browser mode
            choice="1"
        fi
    fi
fi

# Capture the launch exit status so the error handler below is reached even
# under `set -e` (a bare non-zero command would otherwise exit immediately).
launch_status=0
if [ "$choice" == "2" ]; then
    echo ""
    echo "Starting GUISkinDose in Native Window mode..."
    $PYTHON -m guiskindose --mode gui --native || launch_status=$?
else
    echo ""
    echo "Starting GUISkinDose in Browser mode..."
    $PYTHON -m guiskindose --mode gui || launch_status=$?
fi

if [ "$launch_status" -ne 0 ]; then
    echo ""
    echo -e "${RED}[ERROR] The application failed to start.${NC}"
    echo "Try installing dependencies: $PYTHON -m pip install -e \".[gui]\" (or \".[gui-native]\" for native window mode)"
    read -r -p "Press Enter to exit..."
fi
