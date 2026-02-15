from __future__ import annotations

import hashlib
import re
from devmemory.core.git_ai_parser import (
    CommitNote,
    FileAttribution,
    PromptData,
    CommitStats,
    get_commit_diff,
    get_per_file_diffs,
)

MAX_FILE_SNIPPET_CHARS = 2000
MAX_SUMMARY_FILES = 20
MAX_PROMPT_MESSAGE_CHARS = 1500


def _memory_id(sha: str, idx: int) -> str:
    raw = f"{sha}:{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _extract_topics_from_paths(files: list[FileAttribution] | list[str]) -> list[str]:
    topics: set[str] = set()
    paths = []
    for f in files:
        paths.append(f.filepath if isinstance(f, FileAttribution) else f)

    for fp in paths:
        parts = fp.rsplit("/", 1)
        if len(parts) == 2:
            dir_part = parts[0].replace("/", " ").strip()
            if dir_part:
                topics.add(dir_part.split()[-1])

        ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
        lang_map = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "rs": "rust", "go": "go", "java": "java", "rb": "ruby",
            "tsx": "react", "jsx": "react", "vue": "vue",
            "css": "styling", "scss": "styling",
            "sql": "database", "prisma": "database",
            "yml": "config", "yaml": "config", "toml": "config", "json": "config",
            "sh": "shell", "bash": "shell",
            "md": "documentation",
        }
        if ext in lang_map:
            topics.add(lang_map[ext])
        if "dockerfile" in fp.lower():
            topics.add("docker")

    return sorted(topics)


def _extract_topics_from_subject(subject: str) -> list[str]:
    keywords = {
        "fix": "bugfix", "bug": "bugfix",
        "feat": "feature", "feature": "feature", "add": "feature",
        "refactor": "refactoring",
        "test": "testing",
        "doc": "documentation", "docs": "documentation",
        "ci": "ci-cd", "cd": "ci-cd",
        "style": "styling",
        "perf": "performance",
        "chore": "maintenance",
        "build": "build",
        "dep": "dependencies",
    }
    found: list[str] = []
    subject_lower = subject.lower()
    for kw, topic in keywords.items():
        if kw in subject_lower and topic not in found:
            found.append(topic)
    return found


def _extract_tech_entities_from_diff(diff_content: str) -> list[str]:
    entities: set[str] = set()

    for match in re.findall(r'^\+\s*(?:from|import)\s+([\w.]+)', diff_content, re.MULTILINE):
        top_module = match.split(".")[0]
        known = {
            "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
            "typer": "Typer", "click": "Click", "rich": "Rich",
            "httpx": "httpx", "requests": "requests", "aiohttp": "aiohttp",
            "redis": "Redis", "sqlalchemy": "SQLAlchemy", "prisma": "Prisma",
            "pydantic": "Pydantic", "pytest": "pytest",
            "langchain": "LangChain", "openai": "OpenAI", "anthropic": "Anthropic",
            "docker": "Docker", "celery": "Celery",
            "numpy": "NumPy", "pandas": "Pandas", "torch": "PyTorch",
            "transformers": "Transformers",
        }
        if top_module.lower() in known:
            entities.add(known[top_module.lower()])

    for match in re.findall(r'^\+\s*image:\s*["\']?([^\s"\']+)', diff_content, re.MULTILINE):
        image_name = match.split(":")[0].split("/")[-1]
        entities.add(image_name)

    for match in re.findall(r'^\+\s*"([^"]+)":\s*"[\^~>=<]*\d', diff_content, re.MULTILINE):
        known_deps = {
            "react": "React", "next": "Next.js", "vue": "Vue",
            "express": "Express", "fastify": "Fastify",
            "typescript": "TypeScript", "tailwindcss": "Tailwind CSS",
            "webpack": "Webpack", "vite": "Vite", "esbuild": "esbuild",
            "prisma": "Prisma", "drizzle-orm": "Drizzle",
        }
        dep_name = match.lower()
        if dep_name in known_deps:
            entities.add(known_deps[dep_name])

    return sorted(entities)


def _extract_added_lines(diff_content: str, max_chars: int = MAX_FILE_SNIPPET_CHARS) -> str:
    lines: list[str] = []
    total = 0

    for line in diff_content.splitlines():
        if not line.startswith("+"):
            continue
        if line.startswith("+++"):
            continue
        clean = line[1:]
        stripped = clean.strip()
        if not stripped:
            continue
        if total + len(clean) + 1 > max_chars:
            lines.append("... (truncated)")
            break
        lines.append(clean)
        total += len(clean) + 1

    return "\n".join(lines)


def _extract_key_lines(diff_content: str, max_chars: int = MAX_FILE_SNIPPET_CHARS) -> str:
    key_patterns = [
        re.compile(r'^\+\s*(class\s+\w+|def\s+\w+|async\s+def\s+\w+|function\s+\w+)'),
        re.compile(r'^\+\s*(from\s+\w+\s+import|import\s+\w+)'),
        re.compile(r'^\+\s*(image:\s*\S+)'),
        re.compile(r'^\+\s*(export\s+(default\s+)?(class|function|const))'),
        re.compile(r'^\+\s*[A-Z_]+='),
    ]

    key_lines: list[str] = []
    other_lines: list[str] = []

    for line in diff_content.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        clean = line[1:]
        if not clean.strip():
            continue
        is_key = any(p.match(line) for p in key_patterns)
        if is_key:
            key_lines.append(clean)
        else:
            other_lines.append(clean)

    result_lines = key_lines[:]
    total = sum(len(l) + 1 for l in result_lines)

    for line in other_lines:
        if total + len(line) + 1 > max_chars:
            break
        result_lines.append(line)
        total += len(line) + 1

    if total >= max_chars and len(result_lines) < len(key_lines) + len(other_lines):
        result_lines.append("... (truncated)")

    return "\n".join(result_lines)


def _format_prompt_messages(messages: list[dict], max_chars: int = MAX_PROMPT_MESSAGE_CHARS) -> str:
    parts: list[str] = []
    total = 0

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") if isinstance(c, dict) else str(c)
                for c in content
            )
        if not content:
            continue
        text = f"[{role}]: {content}"
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 50:
                parts.append(text[:remaining] + "...")
            break
        parts.append(text)
        total += len(text) + 1

    return "\n".join(parts)


def format_commit_as_memories(
    commit: CommitNote,
    namespace: str = "default",
    user_id: str = "",
) -> list[dict]:
    memories: list[dict] = []
    idx = 0

    file_diffs = get_per_file_diffs(commit.sha)
    all_diff_content = "\n".join(file_diffs.values())

    filepaths = [f.filepath for f in commit.files]
    file_topics = _extract_topics_from_paths(commit.files)
    subject_topics = _extract_topics_from_subject(commit.subject)
    all_topics = sorted(set(file_topics + subject_topics))

    tech_entities = _extract_tech_entities_from_diff(all_diff_content)

    agents: set[str] = set()
    prompt_summaries: list[str] = []
    total_accepted = 0
    total_overridden = 0
    for pd in commit.prompts.values():
        if pd.tool and pd.model:
            agents.add(f"{pd.tool}/{pd.model}")
        elif pd.tool:
            agents.add(pd.tool)
        if pd.messages:
            first_user = ""
            for m in pd.messages:
                if m.get("role") == "user":
                    content = m.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in content
                        )
                    first_user = content
                    break
            if first_user:
                prompt_summaries.append(first_user[:200])
        total_accepted += pd.accepted_lines
        total_overridden += pd.overridden_lines

    summary_parts = [f"Commit: {commit.subject}"]

    if commit.body:
        body_truncated = commit.body[:500]
        summary_parts.append(f"Description: {body_truncated}")

    summary_parts.append(f"Author: {commit.author_name} <{commit.author_email}>")
    summary_parts.append(f"Date: {commit.date}")
    summary_parts.append(f"SHA: {commit.sha[:12]}")

    if agents:
        summary_parts.append(f"Agent: {', '.join(sorted(agents))}")

    if prompt_summaries:
        for i, ps in enumerate(prompt_summaries[:5]):
            summary_parts.append(f"Prompt {i+1}: \"{ps}\"")

    if commit.stats:
        s = commit.stats
        summary_parts.append(f"AI contribution: {s.ai_additions} AI lines, {s.human_additions} human lines")
        if s.ai_accepted:
            summary_parts.append(f"AI acceptance: {s.ai_accepted} lines accepted unchanged")
        if s.mixed_additions:
            summary_parts.append(f"Mixed (AI + human edit): {s.mixed_additions} lines")
        if s.time_waiting_for_ai:
            summary_parts.append(f"Time waiting for AI: {s.time_waiting_for_ai:.0f}s")
        if s.tool_model_breakdown:
            for tool_model, breakdown in s.tool_model_breakdown.items():
                summary_parts.append(f"  {tool_model}: {breakdown.get('ai_additions', 0)} lines")
    elif commit.prompts:
        summary_parts.append(f"Prompts used: {len(commit.prompts)}")
        if total_accepted:
            summary_parts.append(f"AI lines accepted: {total_accepted}")
        if total_overridden:
            summary_parts.append(f"AI lines overridden: {total_overridden}")

    if tech_entities:
        summary_parts.append(f"Technologies: {', '.join(tech_entities)}")

    if filepaths:
        display_files = filepaths[:MAX_SUMMARY_FILES]
        summary_parts.append(f"Files with AI code: {', '.join(display_files)}")
        if len(filepaths) > MAX_SUMMARY_FILES:
            summary_parts.append(f"  ... and {len(filepaths) - MAX_SUMMARY_FILES} more")

    diff_stat = get_commit_diff(commit.sha)
    if diff_stat:
        summary_parts.append(f"Diff summary: {diff_stat}")

    entities = [commit.author_name]
    entities.extend(tech_entities)
    entities.extend(filepaths[:10])

    summary_topics = list(all_topics) if all_topics else ["code-change"]
    if prompt_summaries and "prompt" not in summary_topics:
        summary_topics = ["prompt"] + summary_topics

    memories.append({
        "id": _memory_id(commit.sha, idx),
        "text": "\n".join(summary_parts),
        "memory_type": "semantic",
        "topics": summary_topics,
        "entities": entities,
        "namespace": namespace,
        "user_id": user_id or commit.author_email,
        "session_id": f"git-{commit.sha[:12]}",
    })
    idx += 1

    for filepath, diff_content in file_diffs.items():
        if not diff_content.strip():
            continue

        code_snippet = _extract_key_lines(diff_content)
        if not code_snippet.strip():
            continue

        file_tech = _extract_tech_entities_from_diff(diff_content)
        file_path_topics = _extract_topics_from_paths([filepath])

        file_text_parts = [
            f"File: {filepath}",
            f"Commit: {commit.subject} ({commit.sha[:12]})",
        ]

        file_agents = set()
        for fa in commit.files:
            if fa.filepath == filepath:
                for pid in fa.prompt_lines:
                    pd = commit.prompts.get(pid)
                    if pd and pd.tool:
                        file_agents.add(f"{pd.tool}/{pd.model}" if pd.model else pd.tool)

        if file_agents:
            file_text_parts.append(f"Generated by: {', '.join(sorted(file_agents))}")

        if file_tech:
            file_text_parts.append(f"Technologies: {', '.join(file_tech)}")

        file_text_parts.append(f"Code changes:\n{code_snippet}")

        memories.append({
            "id": _memory_id(commit.sha, idx),
            "text": "\n".join(file_text_parts),
            "memory_type": "episodic",
            "topics": file_path_topics if file_path_topics else ["code-change"],
            "entities": [filepath] + file_tech,
            "namespace": namespace,
            "user_id": user_id or commit.author_email,
            "session_id": f"git-{commit.sha[:12]}",
        })
        idx += 1

    for pid, pd in commit.prompts.items():
        if not pd.messages:
            continue

        formatted_messages = _format_prompt_messages(pd.messages)
        if not formatted_messages.strip():
            continue

        agent_str = f"{pd.tool}/{pd.model}" if pd.model else (pd.tool or "unknown")

        prompt_text_parts = [f"Prompt to {agent_str}:"]
        prompt_text_parts.append(formatted_messages)

        result_parts = []
        if pd.total_additions:
            result_parts.append(f"{pd.total_additions} lines added")
        if pd.total_deletions:
            result_parts.append(f"{pd.total_deletions} lines deleted")
        if pd.accepted_lines:
            acceptance_rate = (pd.accepted_lines / pd.total_additions * 100) if pd.total_additions else 0
            result_parts.append(f"{pd.accepted_lines} accepted ({acceptance_rate:.0f}%)")
        if pd.overridden_lines:
            result_parts.append(f"{pd.overridden_lines} overridden")

        if result_parts:
            prompt_text_parts.append(f"Result: {', '.join(result_parts)}")

        affected_files = []
        for fa in commit.files:
            if pid in fa.prompt_lines:
                affected_files.append(fa.filepath)
        if affected_files:
            prompt_text_parts.append(f"Files affected: {', '.join(affected_files[:10])}")

        prompt_text_parts.append(f"Commit: {commit.subject} ({commit.sha[:12]})")

        prompt_topics = list(all_topics) if all_topics else ["code-change"]
        if "prompt" not in prompt_topics:
            prompt_topics = ["prompt"] + prompt_topics

        prompt_prefix = "Stored AI prompt for this repository. "
        memories.append({
            "id": _memory_id(commit.sha, idx),
            "text": prompt_prefix + "\n".join(prompt_text_parts),
            "memory_type": "semantic",
            "topics": prompt_topics,
            "entities": [pd.human_author or commit.author_name, agent_str] + affected_files[:5],
            "namespace": namespace,
            "user_id": user_id or commit.author_email,
            "session_id": f"git-{commit.sha[:12]}",
        })
        idx += 1

    return memories


def format_commit_without_ai(
    commit: CommitNote,
    namespace: str = "default",
    user_id: str = "",
) -> list[dict]:
    diff_stat = get_commit_diff(commit.sha)
    subject_topics = _extract_topics_from_subject(commit.subject)

    file_diffs = get_per_file_diffs(commit.sha)
    all_diff_content = "\n".join(file_diffs.values())
    tech_entities = _extract_tech_entities_from_diff(all_diff_content)

    text_parts = [
        f"Commit (human-authored): {commit.subject}",
        f"Author: {commit.author_name} <{commit.author_email}>",
        f"Date: {commit.date}",
        f"SHA: {commit.sha[:12]}",
    ]

    if commit.body:
        text_parts.append(f"Description: {commit.body[:500]}")
    if tech_entities:
        text_parts.append(f"Technologies: {', '.join(tech_entities)}")
    if diff_stat:
        text_parts.append(f"Diff summary: {diff_stat}")

    entities = [commit.author_name]
    entities.extend(tech_entities)

    return [{
        "id": _memory_id(commit.sha, 0),
        "text": "\n".join(text_parts),
        "memory_type": "episodic",
        "topics": subject_topics if subject_topics else ["code-change"],
        "entities": entities,
        "namespace": namespace,
        "user_id": user_id or commit.author_email,
        "session_id": f"git-{commit.sha[:12]}",
    }]
