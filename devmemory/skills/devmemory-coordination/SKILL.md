---
name: devmemory-coordination
description: Universal agent coordination to share learnings, skills, and context across all AI agents (Claude, Cursor, Copilot, Mistral, Antigravity) running on this project.
---

# Universal Agent Coordination System

**This skill works with ANY AI coding agent** (Cursor, Claude, Copilot, Mistral, Antigravity, etc.)

All agents share the same memory system. What one agent learns, all agents can use.

## 1. Memory Access Pattern (Universal)

```python
# Get complete context for your task
from devmemory.agent_tools import get_universal_agent_tools
memory = get_universal_agent_tools()
context = memory.get_hierarchical_context("implement authentication system")
```

## 2. Cross-Agent Learning

```python
# Store what you've learned (universal format)
memory.store_agent_learning(
    learning="Use OAuth2 with PKCE for mobile auth to prevent token theft",
    learning_type="semantic",
    topics=["security", "authentication", "mobile"],
    entities=["OAuth2", "PKCE"]
)
```

## 3. Reusable Skills System

```python
# Check if skill exists
skill = memory.get_agent_skill("authentication_pattern")

if not skill:
    # Store new skill for all agents to use
    memory.store_agent_skill(
        skill_name="authentication_pattern",
        skill_description="Secure authentication pattern using JWT with refresh tokens",
        implementation="1. Use short-lived access tokens...",
        use_cases=["Web applications", "Mobile apps"]
    )
```

## 4. Coordination Protocol

```python
# Check who's working on what
coordination = memory.get_hierarchical_context("current work")
active_sessions = coordination["coordination"]["active_sessions"]

# Announce your work
memory.store_agent_learning(
    learning="Currently implementing OAuth2 provider integration",
    topics=["active-work", "coordination"],
    entities=["authentication"]
)
```

## Keep memories relevant
Store:
- Architecture decisions with rationale
- Patterns and conventions
- Gotchas and workarounds
- API quirks and limitations
- Performance optimizations

Avoid:
- Implementation details obvious from code
- Temporary debugging notes
- Personal preferences
- Redundant copies of commit messages
