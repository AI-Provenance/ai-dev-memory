#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux*)     PLATFORM="linux";;
    Darwin*)    PLATFORM="macos";;
    CYGWIN*|MINGW*|MSYS*) PLATFORM="windows";;
    *)          PLATFORM="unknown";;
esac

echo "DevMemory Installer"
echo "==================="
echo ""

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    error "Python not found. Install Python 3.10+: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
info "Python $PYTHON_VERSION"

# Check pip
if ! command -v pip3 &>/dev/null && ! command -v pip &>/dev/null; then
    warn "pip not found, installing..."
    if [ "$PLATFORM" = "linux" ]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y python3-pip
        elif command -v yum &>/dev/null; then
            sudo yum install -y python3-pip
        fi
    elif [ "$PLATFORM" = "macos" ]; then
        brew install python3
    fi
fi

PIP_CMD=""
for cmd in pip3 pip; do
    if command -v "$cmd" &>/dev/null; then
        PIP_CMD="$cmd"
        break
    fi
done

if [ -z "$PIP_CMD" ]; then
    error "pip not available. Install pip: https://pip.pypa.io/"
    exit 1
fi

info "Installing DevMemory..."
$PIP_CMD install -U devmemory

echo ""
info "DevMemory installed!"
echo ""

# Check if in a git repo
if git rev-parse --show-toplevel &>/dev/null 2>&1; then
    REPO_ROOT=$(git rev-parse --show-toplevel)
    echo "Detected git repo: $REPO_ROOT"
    echo ""
    echo "Run one of these to set up:"
    echo ""
    echo "  # Local mode (SQLite, no infrastructure):"
    echo "  devmemory install --mode local"
    echo ""
    echo "  # Cloud mode (Redis AMS, full features):"
    echo "  devmemory install --mode cloud"
    echo ""
else
    echo "Not in a git repository."
    echo ""
    echo "To set up in your project:"
    echo "  cd your-project"
    echo "  devmemory install --mode local"
fi

echo ""
echo "For Sentry integration:"
echo "  npm install @devmemory/sentry"
echo ""
echo "Docs: https://docs.devmemory.ai"
