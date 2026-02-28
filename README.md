# DevMemory 🧠🚀

[![CI](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/devmemory.svg)](https://pypi.org/project/devmemory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**AI code attribution that answers "why?" — for developers and AI agents.**

Built on [Git AI](https://github.com/git-ai-project/git-ai) for capture and [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) for semantic search and recall.

> For local mode we use [sqlite](https://github.com/sqlite/sqlite)

> Status: currently in Beta.


**AI code attribution that answers "why?" — for developers and AI agents.**

DevMemory tracks which AI tool wrote which line of code, then makes that knowledge searchable. Ask "why did we use this pattern?" and get answers backed by commits, prompts, and context.

---

## Quick Install

```bash
# One-line install (local mode)
curl -sSL https://raw.githubusercontent.com/AI-Provenance/ai-dev-memory/main/scripts/install-simple.sh | bash
```

Then in your project:
```bash
devmemory install --mode local
```

---

## Choose Your Setup

### Option 1: Local (SQLite) — Free, No Infrastructure

For tracking AI code attributions locally without external services.

```bash
# 1. Install
pip install devmemory

# 2. Set up in your repo
cd your-project
devmemory install --mode local

# 3. Start coding — commits auto-sync
git commit -m "feat: new login"  # AI attribution tracked automatically
devmemory attribution lookup path/to/file.py  # See who wrote what
```

**What's included:**
- AI code line attribution (SQLite)
- Git hooks for auto-sync
- `devmemory attribution` commands
- Sentry error tracking with AI attributions

### Sentry Integration

When an error hits Sentry, see which AI tool and model wrote the code that caused it.

**Python:**
```python
import sentry_sdk
from devmemory.sentry import create_before_send

sentry_sdk.init(
    dsn="YOUR_SENTRY_DSN",
    before_send=create_before_send(),
)
```

**Node.js / Next.js:**
```bash
npm install @aiprovenance/sentry
```

```javascript
import { createDevMemoryBeforeSend } from "@aiprovenance/sentry";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  beforeSend(event, hint) {
    return createDevMemoryBeforeSend()(event, hint);
  },
});
```

Auto-detects repoId from git remote or `DEVMEMORY_REPO_ID` env var.

This adds `ai_model`, `ai_tool`, `author`, `commit_sha`, and other tags to every Sentry event.

---

### Option 2: Cloud (Redis AMS) — Full Features

> **Note:** Full Cloud mode is coming soon. Some features below require additional setup.

For teams who want semantic search, team stats, and AI agent memory.

```bash
# 1. Install
pip install devmemory

# 2. Start Redis AMS
docker compose --profile debug up -d

# 3. Set up in your repo
cd your-project
devmemory install --mode cloud

# Start using
devmemory why src/auth.py          # Ask why a file looks this way
devmemory search "how do we auth?" # Semantic search
devmemory stats                    # AI vs Human code stats
```

**What's included:**
- Everything in Local mode
- Semantic memory search
- Team code statistics
- Cursor/Claude agent integration
- Context briefings on branch switch

> **Sentry integration (Cloud):** Error tracking with AI attribution is coming soon — requires API call to enrich events.

---

## Why DevMemory?

| For Developers | For AI Agents |
|----------------|----------------|
| "Why did we choose this pattern?" | Start with repo context, not from scratch |
| "Who wrote this — AI or human?" | Remember what previous agents learned |
| Team AI vs Human code stats | Reuse knowledge across sessions |

**With Sentry Integration:** Errors automatically include AI attribution data — see exactly which AI tool and model generated the code that caused the crash.

---

## Commands

### Local Mode
| Command | Description |
|---------|-------------|
| `devmemory attribution lookup <file>` | See who wrote each line |
| `devmemory attribution history <file>` | View attribution history |
| `devmemory sync` | Sync Git AI notes to SQLite |
| `devmemory status` | Check system health |

### Cloud Mode
| Command | Description |
|---------|-------------|
| `devmemory why <file>` | Explain why a file/function looks this way |
| `devmemory search <query>` | Semantic search across all memories |
| `devmemory stats` | AI vs Human code contribution |
| `devmemory attribution lookup <file>` | See who wrote each line |
| `devmemory attribution history <file>` | View attribution history |
| `devmemory sync` | Sync Git AI notes to AMS |
| `devmemory status` | Check system health |

---

## Requirements

- Python 3.10+
- [Git AI](https://usegitai.com/) — for capturing AI code attribution
- (Cloud mode) Docker — for Redis AMS

---

## Learn More

- [Documentation](https://docs.devmemory.ai)
- [GitHub](https://github.com/AI-Provenance/ai-dev-memory)

---

**Stop re-explaining your code. Let DevMemory remember.**
