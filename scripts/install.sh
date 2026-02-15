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
echo "  3. Install devmemory CLI (via uv)"
echo "  4. Set up .env file"
echo "  5. Start the Docker stack"
echo "  6. Configure git hooks, Cursor MCP, and agent coordination rules"
echo ""

# ── Step 1: Prerequisites ──────────────────────────────────────────────────────

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

if ! docker info &>/dev/null 2>&1; then
    error "Docker daemon is not running."
    echo ""
    case "$(uname -s)" in
        Darwin)
            echo "  Start Docker Desktop:"
            echo "    open -a Docker"
            ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "  You appear to be on WSL. Start Docker Desktop from Windows,"
                echo "  or enable the WSL integration in Docker Desktop settings."
            else
                echo "  Start the Docker service:"
                echo "    sudo systemctl start docker"
            fi
            ;;
        *)
            echo "  Please start Docker Desktop or the Docker service."
            ;;
    esac
    echo ""
    echo "  Then re-run:"
    echo "    $0"
    exit 1
fi
info "docker daemon is running"

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

# ── Step 2: Git AI ─────────────────────────────────────────────────────────────

step "[2/6] Checking Git AI..."

GIT_AI_BIN=""
if command -v git-ai &>/dev/null; then
    GIT_AI_BIN="git-ai"
elif [ -x "$HOME/.git-ai/bin/git-ai" ]; then
    GIT_AI_BIN="$HOME/.git-ai/bin/git-ai"
elif git ai version &>/dev/null 2>&1; then
    GIT_AI_BIN="git ai"
fi

if [ -n "$GIT_AI_BIN" ]; then
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

_run_git_ai_config() {
    if command -v git-ai &>/dev/null; then
        git-ai config set prompt_storage notes 2>/dev/null
    elif [ -x "$HOME/.git-ai/bin/git-ai" ]; then
        "$HOME/.git-ai/bin/git-ai" config set prompt_storage notes 2>/dev/null
    elif git ai version &>/dev/null 2>&1; then
        git ai config set prompt_storage notes 2>/dev/null
    fi
}
if _run_git_ai_config; then
    info "Git AI prompt_storage set to notes (prompts in git notes for DevMemory)"
fi

# ── Step 3: Install devmemory CLI via uv ───────────────────────────────────────

step "[3/6] Installing devmemory CLI..."

cd "$SCRIPT_DIR"

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the env so uv is available immediately
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        error "Failed to install uv. Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    info "uv installed"
else
    info "uv $(uv --version | awk '{print $2}')"
fi

uv tool install --editable "$SCRIPT_DIR" --force --quiet
uv tool update-shell --quiet 2>/dev/null || true
info "devmemory installed"

# Ensure devmemory is on PATH for the rest of this script
if ! command -v devmemory &>/dev/null; then
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v devmemory &>/dev/null; then
    error "devmemory not found on PATH after install."
    echo "  Try opening a new terminal, or run:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    exit 1
fi
info "devmemory is on PATH"

# ── Step 4: Environment ────────────────────────────────────────────────────────

step "[4/6] Setting up environment..."

ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    warn ".env file created from .env.example"

    if [ -z "${OPENAI_API_KEY:-}" ]; then
        echo ""
        read -p "Enter your OpenAI API key (or press Enter to skip): " api_key
        if [ -n "$api_key" ]; then
            sed -i.bak "s/your_openai_api_key_here/$api_key/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
            info "API key saved to .env"
        else
            warn "No API key set. Edit .env before starting the stack."
            warn "Memories won't be processed without an OpenAI API key."
        fi
    else
        sed -i.bak "s/your_openai_api_key_here/$OPENAI_API_KEY/" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
        info "API key set from OPENAI_API_KEY environment variable"
    fi
else
    info ".env file already exists"
fi

# ── Step 5: Docker stack ───────────────────────────────────────────────────────

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

# ── Step 6: Configure hooks, MCP, agent rules ─────────────────────────────────

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
