#!/usr/bin/env bash
# DevMemory Simple Installer
# Installs devmemory CLI for local mode (SQLite, free, offline)
# For cloud features, get an API key at https://aiprove.org

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { printf "%b\n" "${GREEN}✓${NC} $1"; }
warn()  { printf "%b\n" "${YELLOW}!${NC} $1"; }
error() { printf "%b\n" "${RED}✗${NC} $1"; }

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "linux";;
        Darwin*)    echo "macos";;
        CYGWIN*|MINGW*|MSYS*) echo "windows";;
        *)          echo "unknown";;
    esac
}

install_uv() {
    local os=$1
    
    if command -v uv &>/dev/null; then
        return 0
    fi
    
    warn "uv not found, installing..."
    
    if [ "$os" = "windows" ]; then
        powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    
    # Add to PATH for current session
    if [ "$os" = "macos" ] || [ "$os" = "linux" ]; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
    
    # Verify installation
    if command -v uv &>/dev/null; then
        return 0
    else
        return 1
    fi
}

echo "DevMemory Installer"
echo "==================="
echo ""

OS=$(detect_os)
info "Detected OS: $OS"

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    error "Python not found. Install Python 3.10+: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2)
info "Python $PYTHON_VERSION"

# Install uv
if ! install_uv "$OS"; then
    error "Failed to install uv. Please install manually: https://astral.sh/uv"
    exit 1
fi

UV_VERSION=$(uv --version 2>&1 | cut -d' ' -f2 || echo "unknown")
info "uv $UV_VERSION"

info "Installing DevMemory..."
uv tool install -U devmemory

# Get installed version
VERSION=$(devmemory version --short 2>/dev/null || echo "unknown")
echo ""
info "DevMemory $VERSION installed!"
echo ""

# Check if in a git repo
if git rev-parse --show-toplevel &>/dev/null 2>&1; then
    REPO_ROOT=$(git rev-parse --show-toplevel)
    printf "%b\n" "${CYAN}Detected git repo: $REPO_ROOT${NC}"
    echo ""
    echo "Run this to set up:"
    echo ""
    printf "%b\n" "  ${GREEN}devmemory install --mode local${NC}"
    echo ""
else
    printf "%b\n" "${CYAN}Not in a git repository.${NC}"
    echo ""
    echo "To set up in your project:"
    echo "  cd your-project"
    echo "  devmemory install --mode local"
fi

echo ""
echo "LOCAL MODE (Free Forever):"
echo "  ✓ SQLite storage"
echo "  ✓ Core attribution"
echo "  ✓ Works offline"
echo ""
echo "CLOUD MODE (Advanced Features):"
echo "  Visit: https://aiprove.org"
echo "  devmemory install --mode cloud --api-key YOUR_KEY"
echo ""
echo "Docs: https://github.com/AI-Provenance/ai-dev-memory"
