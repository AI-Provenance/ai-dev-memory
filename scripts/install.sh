#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }
step()  { echo -e "\n${BOLD}$1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

step "DevMemory Setup"
echo "This script will:"
echo "  1. Check prerequisites (git, docker, python3)"
echo "  2. Install Git AI (if not present)"
echo "  3. Install devmemory CLI"
echo "  4. Set up .env file"
echo "  5. Start the Docker stack"
echo "  6. Configure git hooks, Cursor MCP, and agent coordination rules"
echo ""

step "[1/6] Checking prerequisites..."

if ! command -v git &>/dev/null; then
    error "git is not installed"
    exit 1
fi
info "git $(git --version | awk '{print $3}')"

if ! command -v docker &>/dev/null; then
    error "docker is not installed. Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
info "docker $(docker --version | awk '{print $3}' | tr -d ',')"

if ! docker compose version &>/dev/null 2>&1; then
    error "docker compose is not available"
    exit 1
fi
info "docker compose available"

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | awk '{print $2}')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "Python 3.10+ is required but not found"
    exit 1
fi
info "$PYTHON_CMD $($PYTHON_CMD --version 2>&1 | awk '{print $2}')"

step "[2/6] Checking Git AI..."

if command -v git-ai &>/dev/null || git ai version &>/dev/null 2>&1; then
    info "Git AI is already installed"
else
    warn "Git AI is not installed"
    read -p "Install Git AI now? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo "Installing Git AI..."
        curl -sSL https://usegitai.com/install.sh | bash
        info "Git AI installed"
    else
        warn "Skipping Git AI installation. You can install it later:"
        echo "  curl -sSL https://usegitai.com/install.sh | bash"
    fi
fi

step "[3/6] Installing devmemory CLI..."

if command -v pip &>/dev/null || command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
    command -v pip3 &>/dev/null || PIP_CMD="pip"
else
    PIP_CMD="$PYTHON_CMD -m pip"
fi

cd "$SCRIPT_DIR"

if command -v pipx &>/dev/null; then
    pipx install -e "$SCRIPT_DIR" --force 2>/dev/null && info "devmemory installed via pipx" || {
        $PIP_CMD install -e "$SCRIPT_DIR" && info "devmemory installed via pip"
    }
else
    $PIP_CMD install -e "$SCRIPT_DIR" && info "devmemory installed via pip"
fi

step "[4/6] Setting up environment..."

ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    warn ".env file created from .env.example"

    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo ""
        read -p "Enter your OpenAI API key (or press Enter to skip): " api_key
        if [ -n "$api_key" ]; then
            sed -i "s/your_openai_api_key_here/$api_key/" "$ENV_FILE"
            info "API key saved to .env"
        else
            warn "No API key set. Edit .env before starting the stack."
            warn "Memories won't be processed without an OpenAI API key."
        fi
    else
        sed -i "s/your_openai_api_key_here/$OPENAI_API_KEY/" "$ENV_FILE"
        info "API key set from OPENAI_API_KEY environment variable"
    fi
else
    info ".env file already exists"
fi

step "[5/6] Starting Docker stack..."

cd "$SCRIPT_DIR"
docker compose up -d

echo "Waiting for services to be healthy..."
for i in {1..30}; do
    if curl -sf http://localhost:8000/v1/health >/dev/null 2>&1; then
        info "AMS API is healthy"
        break
    fi
    if [ "$i" -eq 30 ]; then
        error "AMS API did not become healthy in 60 seconds"
        echo "Check logs with: docker compose logs"
        exit 1
    fi
    sleep 2
done

if curl -sf http://localhost:6379 >/dev/null 2>&1 || docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    info "Redis is healthy"
fi

step "[6/6] Configuring hooks, MCP, and agent rules..."

if git rev-parse --show-toplevel &>/dev/null; then
    devmemory install
else
    warn "Not in a git repository. Run 'devmemory install' from a git repo to set up hooks."
fi

echo ""
step "Setup complete!"
echo ""
echo "Quick start:"
echo "  devmemory status         Check everything is working"
echo "  devmemory sync --all     Sync existing Git AI data"
echo "  devmemory search 'query' Search your memories"
echo ""
echo "The Docker stack is running. Manage with:"
echo "  make up       Start stack"
echo "  make down     Stop stack"
echo "  make logs     View logs"
echo "  make debug    Start with RedisInsight (port 16381)"
