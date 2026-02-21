---
name: devmemory-memory
description: Search project memory before starting tasks, and store what you learn (architecture, decisions, gotchas) after making them. Use when starting a new codebase task, bug fix, or feature.
---

# DevMemory: Shared Agent Memory

You have access to a shared project memory via the `agent-memory` MCP server.
This memory persists across all sessions and is shared between every agent working on this project.
Use it as a **knowledgebase** (look up past decisions) and **coordination tool** (leave context for future sessions).

## 1. Before Starting Any Task

**Always search memory first.** Before writing code, look up what's already known to prevent cold start:

```python
search_long_term_memory(text="<describe what you're about to work on>", namespace="{{NAMESPACE}}")
```

Search for a specific topic:
```python
search_long_term_memory(text="...", topics=["<topic>"], namespace="{{NAMESPACE}}")
```

Search for:
- Past decisions related to your task
- Known issues or gotchas in the area you're touching
- Established patterns and conventions
- Previous attempts that failed and why

**Check for Hierarchical Summaries** first before digging into commits:
```python
# Query project-level summaries
search_long_term_memory(text="project summary architecture decisions", topics=["project-summary"], namespace="{{NAMESPACE}}", limit=3)

# Query architecture evolution summaries
search_long_term_memory(text="architecture evolution design patterns", topics=["architecture-summary"], namespace="{{NAMESPACE}}", limit=3)
```

## 2. After Making Significant Decisions

You have two ways to persist knowledge:

### Structured knowledge: update `.devmemory/knowledge/` files

For anything that future agents should know about, **update the knowledge files directly** and then sync:

**When to update knowledge files:**
- Architecture decision (add to `architecture.md`)
- Discovered a gotcha or workaround (add to `gotchas.md`)
- Established a new convention or pattern (add to `conventions.md` — create if needed)
- Added/changed a major dependency and why
- Fixed a non-obvious bug that could regress

**Format for knowledge files:**
```markdown
---
topics: [architecture, decisions]
entities: [Redis, AMS]
---

## Section Title
Content explaining what, why, and any relevant details.
```

### Quick capture via MCP

After updating files, or for a single discovery, store via MCP:

```python
create_long_term_memories(memories=[{
    "text": "<what was decided and why>",
    "memory_type": "semantic",
    "topics": ["<relevant>", "<topics>"],
    "entities": ["<technologies>", "<modules>"],
    "namespace": "{{NAMESPACE}}"
}])
```

## 3. Session Coordination

Use working memory to coordinate across active sessions:

**When starting a large task** — announce what you're working on:
```python
set_working_memory(
    session_id="project-coordination",
    memories=[{
        "text": "Currently refactoring the search command to add LLM synthesis",
        "memory_type": "semantic",
        "topics": ["active-work"]
    }]
)
```
