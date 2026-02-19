# DevMemory 🧠🚀

[![CI](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Provenance/ai-dev-memory/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/devmemory.svg)](https://pypi.org/project/devmemory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

DevMemory is a long‑term memory for AI coding agents that can explain why any file or function looks the way it does and let agents reuse that understanding across sessions without re-reading the whole repo.

Built on [Git AI](https://github.com/git-ai-project/git-ai) for capture and [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) for semantic search and recall.

---

## Why DevMemory

- **`devmemory why` for code archaeology**: Ask why a file or function exists and get a narrative backed by commits, prompts, and code snippets.
- **Semantic search over your repo’s history**: Search “how do we handle auth?” or “why did we switch to Redis?” and get synthesized answers with sources.
- **Agent-ready, session‑to‑session memory**: Coding agents can fetch recent and relevant memories at the start of a task and write new ones when they finish, instead of re‑parsing the codebase and burning tokens every session.

If Git AI tracks who wrote which line and Entire checkpoints how agents worked, DevMemory answers what the team actually learned, why the code ended up this way, and gives agents a fast way to reuse that knowledge next time.

---

## `devmemory why` (hero feature)

```bash
devmemory why src/auth.py
devmemory why src/auth.py login
devmemory why src/auth.py --raw
devmemory why src/auth.py --verbose
```

`devmemory why` pulls together:

- Commit summaries
- Per-file code snapshots
- Prompt-level context
- Human knowledge from `.devmemory/knowledge/*.md`

and turns them into an explanation of how and why a file or symbol evolved, plus the sources it used.

Typical questions it answers:

- Why do we use this pattern here instead of an alternative?
- When did this behavior change and what bug or feature drove it?
- Which agent and prompts were involved in this refactor?

---

## Quick start

### Prerequisites

- Git
- Docker and Docker Compose
- Python 3.10+
- OpenAI API key (for embeddings and answer synthesis)
- [Git AI](https://usegitai.com/) (for AI code attribution capture)

### One-line setup

```bash
bash scripts/install.sh
```

This script checks your environment, installs the CLI with `uv`, starts Redis plus AMS and MCP, configures git hooks, and wires DevMemory into Cursor.

### Manual setup

```bash
git clone https://github.com/devmemory/devmemory
cd devmemory

cp .env.example .env

make up

uv tool install --editable .

cd /path/to/your/project
devmemory install

devmemory status
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

`devmemory install` wires DevMemory into Cursor so agents can:

1. Use **MCP tools** like `search_long_term_memory` to pull in recent and relevant memories instead of asking the LLM to rediscover context from raw code.
2. Call `create_long_term_memories` at the end of a task to store what changed and why, so future sessions start with that knowledge.
3. Read `.devmemory/CONTEXT.md` on branch switch for a compact briefing instead of re‑evaluating the entire project on every run.

Over time this creates a compounding loop: each agent session leaves the repo a little better documented for the next one, while saving tokens and latency by reusing existing memory.

---

## Auto-summarization

DevMemory can automatically generate LLM-powered summaries for each commit during sync. These summaries capture:

- **Intent**: Why the change was made and what problem it solves
- **Outcome**: What was actually implemented
- **Learnings**: Insights discovered during implementation
- **Friction points**: Blockers, tradeoffs, or challenges encountered
- **Open items**: Follow-ups, known limitations, or TODOs

**Benefits for agents:**

- **Token efficiency**: Agents read concise summaries (100-300 tokens) instead of parsing full commit diffs
- **Better search relevance**: Semantic search finds summaries that explain "why we added retry logic" faster than scanning code
- **Faster onboarding**: Agents quickly catch up on recent changes by reading summaries instead of analyzing code
- **Intent preservation**: The "why" behind changes is preserved even when commit messages are brief

**Enable auto-summarization:**

```bash
devmemory config set auto_summarize true
```

Summaries are generated non-blocking during `devmemory sync`—failures are logged but don't stop the sync process. Each summary is stored as a semantic memory with the `commit-summary` topic, making them easily searchable.

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
  "user_id": "",
  "auto_summarize": false
}
```

**Configuration options:**

- `auto_summarize`: Enable automatic LLM-powered commit summaries (default: `false`). When enabled, each commit synced generates a narrative summary capturing intent, outcome, learnings, and friction points.

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
