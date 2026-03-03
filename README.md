# DevMemory 🧠🚀

[![CI](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/devmemory.svg)](https://pypi.org/project/devmemory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Track which AI wrote which line of code.**

DevMemory automatically captures AI code attribution and makes it queryable. Know which AI tool wrote what, see diffs, and integrate with Sentry for AI-attributed error tracking.

---

## Quick Start

```bash
# One-line install
curl -sSL https://raw.githubusercontent.com/AI-Provenance/ai-dev-memory/main/scripts/install.sh | bash
```

**Or install manually:**

```bash
# 1. Install
pip install devmemory

# 2. Setup in your repo (one-time)
cd your-project
devmemory install --mode local

# 3. That's it! Make commits normally
git commit -m "feat: new login"
# ✓ AI attribution auto-synced to SQLite

# 4. Query attributions anytime
devmemory attribution lookup src/main.py 42
devmemory attribution lookup src/main.py 42 --diff  # Show git diff
```

**Everything is automatic** — no manual sync needed. After installation, every commit automatically syncs AI attribution data to local SQLite.

---

## What You Get

### 🔍 **Line Attribution**
See who wrote any line of code:
```bash
devmemory attribution lookup src/auth.py 15

# Output:
# File: src/auth.py
# Line: 15
# Commit: abc123
# ✓ AI-generated
# Tool: opencode
# Model: opencode/trinity-large
# Prompt ID: 7a66807c780f
```

### 📝 **Git Diff Integration**
See the actual changes when the line was added:
```bash
devmemory attribution lookup src/auth.py 15 --diff

# Shows:
# - Which commit modified the line
# - Full git diff with syntax highlighting
# - Target line marked with "<<< TARGET LINE"
```

### 📜 **Attribution History**
View all commits that touched a file:
```bash
devmemory attribution history src/auth.py
```

### 🚨 **Sentry Integration**
Errors in production show which AI wrote the buggy code:
```python
import sentry_sdk
from devmemory.sentry import create_before_send

sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",
    before_send=create_before_send(),
)
```

Sentry events automatically include:
- `ai_tool` — which AI wrote the code
- `ai_model` — which model was used
- `commit_sha` — which commit introduced it
- `prompt_id` — link back to the original prompt

---

## Installation Details

### Prerequisites
- Python 3.10+
- [Git AI](https://usegitai.com/) — auto-installs AI attribution tracking

### Setup Steps

```bash
# Install DevMemory
pip install devmemory

# Initialize in your repo
devmemory install --mode local

# What this does:
# ✓ Installs git hooks (auto-sync on every commit)
# ✓ Creates .devmemory/attributions.db (SQLite)
# ✓ Configures git-ai for prompt capture
```

### After Installation

Just work normally:
- Make changes with AI tools (Cursor, Claude, OpenCode etc.)
- Git AI captures attribution automatically
- DevMemory syncs to SQLite after each commit
- Query anytime with `devmemory attribution` commands

**No manual sync needed** — it's all automatic!

---

## Commands

### Attribution Commands
| Command | Description |
|---------|-------------|
| `devmemory attribution lookup <file> <line>` | Who wrote this line? |
| `devmemory attribution lookup <file> <line> --diff` | Show git diff for this line |
| `devmemory attribution show <file>` | All attributions for a file |
| `devmemory attribution list` | List all tracked files |
| `devmemory attribution history <file>` | Commit history for a file |

### Utility Commands
| Command | Description |
|---------|-------------|
| `devmemory status` | Check system health |
| `devmemory sync --latest` | Manual sync (only if needed) |

---

## How It Works

1. **Capture**: [Git AI](https://usegitai.com/) tracks which AI tool wrote each line
2. **Store**: DevMemory stores attributions in local SQLite (`.devmemory/attributions.db`)
3. **Auto-sync**: Git hooks sync after every commit — zero manual work
4. **Query**: CLI commands query SQLite instantly, offline

**Data stays local** — works offline, no cloud required.

---

## Cloud Mode COMING SOON...

For teams wanting advanced features:
- Semantic search across codebase
- Team analytics dashboard
- AI agent context integration
- Shared attribution database

```bash
devmemory install --mode cloud --api-key YOUR_KEY
```

Get API key at [aiprove.org](https://aiprove.org)

---

## Requirements

- **Python 3.10+**
- **Git AI** — auto-installed during setup
- **SQLite** — included with Python

---

**Stop wondering "who wrote this?" — DevMemory knows.**
