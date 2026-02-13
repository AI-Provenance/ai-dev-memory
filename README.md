# DevMemory 🚀🧠

[![CI](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/devmemory.svg)](https://pypi.org/project/devmemory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **TL;DR**: DevMemory is a long‑term memory for your AI coding agents.  
> It remembers *why* code was written, *how* it changed, and *what* your team learned — then feeds that back into your agents. No more “reinvent the bug” speedruns. 🐛🔥

Built on [Git AI](https://github.com/git-ai-project/git-ai) for silent capture and [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) for semantic search and recall.

---

## 💡 What DevMemory Does (in human terms)

- 🪝 **Hooks into your git workflow** via Git AI notes  
- 🧬 **Extracts rich memories**:
  - Commit summaries (who, what, why, which agent/model, how much AI)
  - Per‑file code snippets
  - Prompt‑level context with acceptance metrics
- 🧠 **Stores everything in Redis AMS** as semantic vectors
- 🔍 **Lets you ask**:  
  *“How do we handle auth?”* → it searches, then LLM‑synthesizes an actual answer with sources  
- 🧾 **Ships a knowledge protocol**: `.devmemory/knowledge/*.md` + CLI + Cursor rules so humans and agents keep the docs alive together

If Entire saves *how* agents worked and Git AI tracks *who wrote which line*, DevMemory is the part that answers *“Okay, but what did we actually learn?”*.

---

## 🧮 How It Works

```text
Developer commits code
        │
        ▼
Git AI captures AI attribution, prompts, agent/model info
        │
        ▼
DevMemory syncs enriched memories to Redis AMS (automatic via post-commit hook)
        │
        ├─► Semantic search via CLI (with LLM-synthesized answers)
        ├─► MCP recall in Cursor IDE (agents search memory before coding)
        └─► Context briefing auto-generated on branch switch
```

**The knowledge loop:**

1. **Capture** – Git AI silently records AI code attribution, prompts, and agent/model info on every commit
2. **Enrich** – DevMemory extracts three layers per commit: enriched summary, per‑file code snapshots, and prompt‑level context with acceptance metrics
3. **Search** – Semantic vector search with LLM‑powered answer synthesis (RAG over your git history)
4. **Recall** – Cursor agents read memory via MCP before writing code, and persist new decisions after
5. **Learn** – Human‑curated knowledge files (`.devmemory/knowledge/*.md`) feed the same store, capturing architecture decisions and gotchas

> 🧵 Think of it as `git log` + “what we should have written in the ADR” + your AI agents actually reading it.

---

## 🎥 Demo (what it *feels* like)

Imagine:

```bash
devmemory status                    # ✅ Stack + hooks look good
git commit -am "feat: add user auth"   # You used an AI agent heavily

# Normally the post-commit hook runs this for you in the background:
#   (sleep 2 && devmemory sync --latest 2>/dev/null) &
# but you can also trigger it manually:
devmemory sync --latest
devmemory search "how do we handle auth in this service?"
```

You get:

- A concise answer synthesized by the LLM (RAG), describing:
  - Which files implement auth
  - Which agent/model was used
  - Key decisions (e.g., why JWT vs sessions)
- A **Sources** table listing:
  - Commit summaries
  - Relevant per‑file code snippets
  - The original prompts that drove the changes

Sample search result:

```
$ devmemory search "why we use redis memory server instead of other databases?"

Searching for: why we use redis memory server instead of other databases?
Synthesizing answer...

╭────────────────────────────────────────────────────────────── Answer ───────────────────────────────────────────────────────────────╮
│                                                                                                                                     │
│  Short answer: because Redis Agent Memory Server (AMS) already provides the exact semantic-memory features we need (embeddings,     │
│  topic extraction, NER, deduplication) while being battle‑tested infra, so it reduces operational complexity and keeps the CLI      │
│  lightweight.                                                                                                                       │
│                                                                                                                                     │
│  Details / evidence from the repo:                                                                                                  │
│                                                                                                                                     │
│   • AMS handles embeddings, topic extraction and NER internally and provides built‑in memory deduplication (see                     │
│     .devmemory/knowledge/architecture.md, commit b0abbb04ad13).                                                                     │
│   • The same AMS image serves both REST (port 8000) and MCP (port 9050) endpoints used by the CLI (see docker-compose.yml and       │
│     ams_client.py; feature enable commit f025d01e107c).                                                                             │
│   • README and ams_client.py show we store semantic vectors in Redis AMS and call its /v1/long-term-memory APIs, avoiding the need  │
│     to run a separate vector DB (README.md commit 2b7602a5318a and devmemory/core/ams_client.py).                                   │
│                                                                                                                                     │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

Sources (10 relevant, 20 filtered out)

 #    Score    Type        Source                                                                      
 1    0.302    semantic    Why Redis Agent Memory Server                                               
 2    0.614    semantic    Memory Types and Their Purpose                                              
 3    0.613    semantic    feat: enable devmemory CLI with redis AMS and git-ai (f025d01e107c)         
 4    0.641    semantic    feat: add more metadata from the session to the memory (4ccf7529bd4e)       
 5    0.671    semantic    fix: use the --quite to show the one line update (139d559bdaa0)             
 6    0.677    semantic    Fix: terminal hang issue and the correct saved memories coun (daf56666f1f1) 
 7    0.512    episodic    .devmemory/knowledge/architecture.md (b0abbb04ad13)                         
 8    0.550    episodic    devmemory/core/ams_client.py (f025d01e107c)                                 
 9    0.588    episodic    README.md (2b7602a5318a)                                                    
 10   0.561    episodic    docker-compose.yml (f025d01e107c)                    
```

Auto-sync example:

![auto-sync.gif](./docs/auto-sync.gif)

---

## 🚀 Quick Start

### Prerequisites

- Git
- Docker + Docker Compose
- Python 3.10+
- OpenAI API key (for embeddings and answer synthesis)
- [Git AI](https://usegitai.com/) (for AI code attribution capture)

### One‑Line Setup

```bash
bash scripts/install.sh
```

This script:

- Checks Docker / Python / Git AI
- Sets up `.env` from `.env.example`
- Starts Redis + AMS + MCP via Docker
- Installs the `devmemory` CLI
- Configures git hooks + Cursor MCP + agent rules in the current repo

### Manual Setup

```bash
git clone https://github.com/devmemory/devmemory
cd devmemory

# Set up environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start the stack
make up

# Install the CLI
pip install -e .

# Set up hooks, MCP config, and Cursor rules in your project
cd /path/to/your/project
devmemory install

# Check everything works
devmemory status
```

---

## ⌨️ CLI Commands

### Core workflow 🧠

```bash
devmemory sync                       # Sync unsynced Git AI commits to Redis
devmemory sync --latest              # Sync only the latest commit
devmemory sync --all                 # Re-sync all commits
devmemory sync --dry-run             # Preview what would be synced
devmemory search "how do we auth"    # Semantic search with LLM-synthesized answer
devmemory search "auth" -n 5         # Limit results
devmemory search "auth" --raw        # Raw results without LLM synthesis
devmemory status                     # Show system health, sync state, hooks
```

### Knowledge management 📚

```bash
devmemory add "We chose Redis over Postgres for vector search because..." --topic architecture
devmemory add --interactive          # Interactive mode with prompts
devmemory learn                      # Sync .devmemory/knowledge/*.md into memory store
devmemory learn --dry-run            # Preview what would be synced
devmemory context                    # Generate .devmemory/CONTEXT.md from git state + memory
```

### Setup and config ⚙️

```bash
devmemory install                    # Set up git hooks + Cursor MCP + agent rules
devmemory install --skip-hook        # Skip hook installation
devmemory install --skip-rule        # Skip Cursor agent rules
devmemory config show                # Show current config
devmemory config set endpoint URL    # Change AMS endpoint
devmemory config reset               # Reset to defaults
```

---

## 📚 Knowledge Files

DevMemory supports human‑curated knowledge in `.devmemory/knowledge/*.md`.  
Each markdown section (`## heading`) becomes a separate searchable memory.

```text
.devmemory/
├── CONTEXT.md              # Auto-generated context briefing (gitignored)
└── knowledge/
    ├── architecture.md     # Architecture decisions and rationale
    ├── gotchas.md          # Known issues and workarounds
    └── conventions.md      # Coding patterns and project rules
```

Knowledge files use frontmatter for metadata:

```markdown
---
topics: [architecture, decisions]
entities: [Redis, AMS]
---

## Why We Chose Redis

We chose Redis with vector search over dedicated vector DBs
because it's already part of our stack and reduces complexity.
```

Run `devmemory learn` to sync knowledge files into the memory store.  
Both automated capture (Git AI) **and** human knowledge feed the same searchable store.

> 🧠 Pro tip: Treat `.devmemory/knowledge/` like living ADRs. Small, focused, and updated often.

---

## 🤝 Cursor Agent Integration

`devmemory install` sets up three things for Cursor:

1. **MCP server config** (`~/.cursor/mcp.json`) – Agents can search and write to the memory store via MCP tools (`search_long_term_memory`, `create_long_term_memories`, etc.)
2. **Agent behavior rules** (`.cursor/rules/devmemory.mdc`) – Instructs agents to search memory before coding, persist decisions after significant work, and maintain knowledge files
3. **Context rule** (`.cursor/rules/devmemory-context.mdc`) – Agents read `.devmemory/CONTEXT.md` at task start for a pre‑built briefing

The result is a **compounding loop**: each agent session makes the next one smarter.  
Your AI stops acting like a goldfish and starts acting like a teammate. 🐠➡️🧑‍💻

---

## 🪝 Git Hooks

DevMemory installs two git hooks:

| Hook | What it does |
|------|--------------|
| `post-commit`   | Runs `devmemory sync --latest` in background (auto‑syncs after every commit) |
| `post-checkout` | Runs `devmemory context --quiet` (refreshes context briefing on branch switch) |

---

## 🏗 Architecture

```text
┌─────────────────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Developer Machine         │     │  Docker Stack     │     │  Cursor IDE     │
│                             │     │                   │     │                 │
│  Git AI (git hooks)         │     │  Redis Stack      │     │  MCP Client     │
│         │                   │     │    ▲              │     │       │         │
│         ▼                   │     │    │              │     │       ▼         │
│  Git Notes (refs/ai)        │     │  AMS API (:8000)  │     │  MCP Server     │
│         │                   │     │    ▲              │     │  (:9050)        │
│         ▼                   │     │    │              │     │                 │
│  devmemory sync ────────────┼─────┼────┘              │     │                 │
│                             │     │                   │     │                 │
│  devmemory search ──────────┼─────┼────► AMS Search ──┼─────┼──► LLM synth    │
│                             │     │                   │     │                 │
│  .devmemory/knowledge/*.md  │     │                   │     │  Agent rules    │
│         │                   │     │                   │     │  (.cursor/rules)│
│  devmemory learn ───────────┼─────┼────┘              │     │                 │
│                             │     │                   │     │                 │
│  devmemory context ─────────┼─────┼────► .devmemory/CONTEXT.md              │
└─────────────────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## 🧾 What Gets Captured

DevMemory extracts three memory layers from each Git AI commit:

| Layer          | Type     | What it contains                                                                 | Answers                                  |
|----------------|----------|----------------------------------------------------------------------------------|------------------------------------------|
| Commit summary | semantic | Agent/model, prompts used, AI contribution stats, acceptance metrics, technologies, files | “Which agent was used?”, “How much AI code?” |
| Per-file code  | episodic | Code snippets from diffs with key lines (imports, class/function defs)          | “How do we call the API?”, “What client for Redis?” |
| Prompt context | semantic | Actual prompt text, acceptance rate, affected files                             | “What prompts were used?”, “What was the developer asking?” |

Unique data points captured via Git AI and surfaced by DevMemory:
- **AI vs human lines** per commit
- **Acceptance rate** (lines accepted unchanged vs overridden)
- **Time waiting for AI** per commit
- **Agent and model** used (Cursor, Copilot, Claude Code, etc.)

---

## 🐳 Docker Stack

The `docker-compose.yml` runs:

| Service | Port | Description |
|---------|------|-------------|
| redis | 6379 | Redis Stack (vector search, JSON, streams) |
| api | 8000 | Agent Memory Server REST API |
| mcp | 9050 | MCP server for Cursor IDE (SSE mode) |
| redis-insight | 16381 | RedisInsight UI (debug profile only) |

```bash
make up       # Start stack
make down     # Stop stack
make logs     # View logs
make debug    # Start with RedisInsight
make clean    # Stop and remove volumes
make verify   # Run verification checks
```

---

## 🌍 How DevMemory Fits the Ecosystem

| Tool | What it does | Data store |
|------|-------------|------------|
| [Git AI](https://usegitai.com/) | Captures AI code attribution and prompts | Git Notes + SQLite |
| [Entire](https://entire.io/) | Captures agent sessions/checkpoints | Git branch |
| **DevMemory** | **Turns captured data into searchable, evolving team knowledge** | **Redis AMS** |

Git AI and Entire are **capture tools**.  
DevMemory is a **memory and knowledge tool** — it makes captured data searchable via semantic vector search, synthesizes answers with LLM, and feeds context back to AI agents automatically.

---

## ⚙️ Configuration

Config is stored in `~/.devmemory/config.json`:

```json
{
  "ams_endpoint": "http://localhost:8000",
  "mcp_endpoint": "http://localhost:9050",
  "namespace": "default",
  "user_id": ""
}
```

Environment variables (in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Used for embeddings and answer synthesis |
| `GENERATION_MODEL` | `gpt-5-mini` | Model for LLM answer synthesis |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model for vector embeddings |

---

## 🧑‍💻 Contributing

Contributions, bug reports, and wild feature ideas are very welcome. 💌  
See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details on running the stack, tests, and linting.

If you build something cool with DevMemory, please open an issue or PR and show it off. ✨

---

## ⭐️ Supporting the Project

If DevMemory helps you or your team:

- Star the repo on GitHub ⭐
- Tell your AI‑obsessed friends
- Open issues with real‑world workflows you’d like memory support for

Happy shipping — and may your agents never forget another architecture decision again. 🧠📦🚀
